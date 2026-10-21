"""
LoanMate realtime voice agent — the new primary voice path.

    React (LiveKit React SDK)
        -> LiveKit WebRTC
        -> LiveKit AgentSession
        -> Gemini Live (native realtime audio in/out, via livekit-plugins-google)
        -> LoanMate deterministic tools (backend/tools/*)
        -> Gemini Live audio back
        -> LiveKit
        -> React

This deliberately does NOT use faster-whisper, edge-tts, or the custom
RMS-based VAD in backend/voice_agent/agent.py — Gemini Live handles speech
understanding, turn detection/endpointing, interruption and speech
synthesis natively over one realtime connection. Those legacy pieces stay
in the repo only for the Streamlit demo path.

Run as a standalone worker process (separate from the FastAPI/uvicorn
process):

    python -m backend.voice_agent.realtime_agent dev      # local dev
    python -m backend.voice_agent.realtime_agent start    # production

The worker registers under a fixed agent_name and only joins rooms that
explicitly request it via room-config agent dispatch (see
backend/routes/realtime.py), so it never auto-joins unrelated rooms.
"""

from __future__ import annotations

import json
import logging
import time

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from google.genai import types as genai_types
from livekit.plugins.google.realtime import RealtimeModel

from backend.config import settings
from backend.rag.rag_service import RAGService
from backend.services import call_records
from backend.services.loan_service import LoanService
from backend.tools import calculator_tools, loan_tools
from backend.voice_agent.call_context import CallContext, build_call_context
from backend.voice_agent.prompts import (
    build_inbound_instructions,
    build_outbound_instructions,
    build_system_instructions,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "loanmate-realtime"
REALTIME_MODEL = "gemini-3.8-live"


class LoanMateAgent(Agent):
    """Realtime agent with LoanMate's deterministic tools bound to one customer.

    Shared by both call directions; InboundLoanMateAgent and
    OutboundLoanMateAgent below add the tools that only make sense for
    that direction, so an inbound call can't log a campaign outcome and
    an outbound call can't open service tickets.
    """

    def __init__(self, call_context: CallContext, customer_context: dict | None, session_id: str | None = None):
        super().__init__(instructions=build_system_instructions(call_context))
        self._call_context = call_context
        self._customer_context = customer_context
        self._session_id = session_id

    @function_tool()
    async def get_emi(self, ctx: RunContext) -> str:
        """Get the customer's current monthly EMI (loan installment) amount.

        Call this whenever the customer asks about their EMI, monthly payment,
        or installment amount.
        """
        emi = loan_tools.get_emi(self._customer_context)
        if emi is None:
            return "No active loan was found for this customer."
        return f"The customer's current monthly EMI is ₹{emi:,.0f}."

    @function_tool()
    async def get_outstanding_balance(self, ctx: RunContext) -> str:
        """Get the customer's current outstanding loan balance — how much
        principal is still left to repay.
        """
        balance = loan_tools.get_outstanding_balance(self._customer_context)
        if balance is None:
            return "No active loan was found for this customer."
        return f"The outstanding balance is ₹{balance:,.0f}."

    @function_tool()
    async def get_next_payment(self, ctx: RunContext) -> str:
        """Get the due date of the customer's next EMI payment."""
        due_date = loan_tools.get_next_payment(self._customer_context)
        if due_date is None:
            return "No active loan was found for this customer."
        return f"The next EMI is due on {due_date}."

    @function_tool()
    async def get_loan_status(self, ctx: RunContext) -> str:
        """Get the current status of the customer's loan, e.g. Active, Closed, or Overdue."""
        status = loan_tools.get_loan_status(self._customer_context)
        if status is None:
            return "No active loan was found for this customer."
        return f"The loan status is {status}."

    @function_tool()
    async def get_remaining_tenure(self, ctx: RunContext) -> str:
        """Get how many months are left on the customer's loan tenure."""
        months = loan_tools.get_remaining_tenure(self._customer_context)
        if months is None:
            return "No active loan was found for this customer."
        return f"{months} months remain on the loan."

    @function_tool()
    async def get_payment_history(self, ctx: RunContext) -> str:
        """Get a summary of the customer's payment schedule / history.

        Note: this demo dataset has no transaction-level payment history,
        only the current EMI schedule — say so honestly if asked for past
        payments.
        """
        history = loan_tools.get_payment_history(self._customer_context)
        return json.dumps(history)

    @function_tool()
    async def calculate_prepayment(self, ctx: RunContext, prepayment_amount: float) -> str:
        """Calculate the effect of a lump-sum prepayment on the customer's loan
        — the new outstanding balance and reduced EMI.

        Args:
            prepayment_amount: The amount in rupees the customer wants to
                prepay, e.g. 200000 for "2 lakh".
        """
        loan = loan_tools.get_loan_details(self._customer_context)
        if not loan:
            return "No active loan was found for this customer."
        result = calculator_tools.calculate_prepayment(
            outstanding=loan["outstanding_amount"],
            annual_rate=loan["interest_rate"],
            remaining_months=loan["remaining_tenure"],
            prepayment_amount=prepayment_amount,
        )
        if result["loan_closed"]:
            return f"That prepayment would fully close the loan — no more EMIs needed."
        return (
            f"After prepaying ₹{prepayment_amount:,.0f}, the new outstanding balance "
            f"would be ₹{result['new_outstanding']:,.0f}, and the EMI would drop from "
            f"₹{result['current_emi']:,.0f} to ₹{result['new_emi']:,.0f}."
        )

    @function_tool()
    async def compare_tenures(self, ctx: RunContext, tenure_years: list[int]) -> str:
        """Compare EMI and total interest across different loan tenure options.

        Args:
            tenure_years: The tenure options to compare, in years, e.g. [5, 10].
        """
        loan = loan_tools.get_loan_details(self._customer_context)
        if not loan:
            return "No active loan was found for this customer."
        months = [y * 12 for y in tenure_years]
        comparison = calculator_tools.compare_tenures(
            loan["loan_amount"], loan["interest_rate"], months
        )
        parts = [
            f"{c['tenure_months'] // 12} years: EMI ₹{c['emi']:,.0f}, total interest ₹{c['total_interest']:,.0f}"
            for c in comparison
        ]
        return "; ".join(parts)

    @function_tool()
    async def calculate_loan_eligibility(
        self,
        ctx: RunContext,
        monthly_income: float,
        proposed_amount: float,
        tenure_years: int = 5,
    ) -> str:
        """Estimate whether the customer would be eligible for a new loan
        based on their income. This is a rough demo affordability check, not
        a real underwriting decision.

        Args:
            monthly_income: The customer's monthly income in rupees.
            proposed_amount: The new loan amount being considered, in rupees.
            tenure_years: The proposed tenure in years (default 5).
        """
        loan = loan_tools.get_loan_details(self._customer_context)
        existing_emi = loan["emi"] if loan else 0.0
        rate = loan["interest_rate"] if loan else 10.0
        result = calculator_tools.calculate_loan_eligibility(
            monthly_income=monthly_income,
            existing_emi=existing_emi,
            proposed_amount=proposed_amount,
            annual_rate=rate,
            tenure_months=tenure_years * 12,
        )
        return (
            f"The estimated EMI for the new loan would be ₹{result['proposed_emi']:,.0f}. "
            f"Based on income, the customer is {result['status'].replace('_', ' ')}."
        )

    @function_tool()
    async def search_loan_knowledge(self, ctx: RunContext, query: str, top_k: int = 3) -> str:
        """Search LoanMate's knowledge base for information about loan
        products, policies, and general FAQs — NOT for this customer's own
        account data. Use this for questions about what LoanMate offers or
        how its policies work in general: loan products (personal, home,
        education, car, gold, business, top-up loans), prepayment,
        foreclosure, missed-EMI and penal-charge policy, eligibility rules,
        required documents, RBI rules and borrower rights (Key Fact
        Statement, interest-rate reset, document return, recovery conduct,
        ombudsman), credit scores, KYC, government schemes (PMAY,
        education-loan subsidies), tax benefits on loans, ways to pay an
        EMI (NACH, UPI AutoPay), loan settlement vs closure, home loan
        balance transfer, insurance sold with loans, customer rights,
        fraud safety, and general loan/banking FAQs.

        This is a semantic (meaning-based) search over LoanMate's demo
        knowledge documents, not a customer data lookup — never use it for
        the customer's own EMI, balance, due date, or loan status; those
        have their own dedicated tools.

        Args:
            query: The customer's question or topic, in their own words —
                e.g. "what documents do I need for a personal loan",
                "prepayment charges", "what happens if I miss an EMI".
            top_k: How many knowledge snippets to retrieve (default 3).
        """
        t0 = time.monotonic()
        result = await RAGService.search(query, top_k)
        logger.info("[RAG] query=%r latency=%.0fms", query, (time.monotonic() - t0) * 1000)
        return result


class InboundLoanMateAgent(LoanMateAgent):
    """The customer called the bank: a service desk that can raise requests."""

    @function_tool()
    async def raise_service_request(self, ctx: RunContext, request_type: str, details: str = "") -> str:
        """Raise a service request for something the bank must action after
        this call, and get a reference number to read back to the customer.

        Args:
            request_type: One of account_statement, no_dues_certificate,
                foreclosure_quote, interest_certificate, document_return,
                update_contact_details, emi_date_change, restructuring_request,
                complaint, fraud_report, human_callback.
            details: A short note of what the customer asked for, in their words.
        """
        record = call_records.raise_service_request(
            customer_id=self._call_context.customer_id,
            request_type=request_type,
            details=details,
            session_id=self._session_id,
        )
        return f"Service request raised: {record['label']}, reference number {record['reference']}."


class OutboundLoanMateAgent(LoanMateAgent):
    """The bank called the customer for one campaign: records how it went."""

    @function_tool()
    async def record_call_outcome(
        self,
        ctx: RunContext,
        outcome: str,
        promised_date: str | None = None,
        promised_amount: float | None = None,
        callback_time: str | None = None,
        notes: str = "",
    ) -> str:
        """Record the outcome of this outbound call. Call exactly once, near
        the end of the call.

        Args:
            outcome: One of callback_requested, not_interested, do_not_call,
                wrong_person, no_response, plus for an EMI reminder:
                will_pay_on_time, promise_to_pay, already_paid,
                payment_difficulty; for an overdue follow-up: promise_to_pay,
                already_paid, payment_difficulty, dispute; for a KYC update:
                will_update_kyc, already_updated; for a product update:
                interested, needs_more_info.
            promised_date: The date the customer promised to pay, if any, e.g. "2026-10-25".
            promised_amount: The amount in rupees the customer promised to pay, if any.
            callback_time: When the customer asked to be called back, if any.
            notes: One short sentence summarising the call.
        """
        try:
            call_records.record_call_outcome(
                customer_id=self._call_context.customer_id,
                outbound_reason=self._call_context.outbound_reason or "emi_reminder",
                outcome=outcome,
                promised_date=promised_date,
                promised_amount=promised_amount,
                callback_time=callback_time,
                notes=notes,
                session_id=self._session_id,
            )
        except ValueError as e:
            return str(e)
        return f"Call outcome recorded: {outcome}."


async def entrypoint(ctx: JobContext) -> None:
    t_job_start = time.monotonic()
    await ctx.connect()

    try:
        metadata = json.loads(ctx.job.metadata) if ctx.job.metadata else {}
    except json.JSONDecodeError:
        metadata = {}

    customer_id = metadata.get("customer_id", "CUST001")
    session_id = metadata.get("session_id")
    call_mode = metadata.get("call_mode", "inbound")
    outbound_reason = metadata.get("outbound_reason")
    language_hint = metadata.get("language", "english")

    customer_context = LoanService.get_customer_with_loans(customer_id)
    if not customer_context:
        logger.warning("[REALTIME] Unknown customer_id=%s — proceeding with no loan context", customer_id)
        customer_context = {"customer": {}, "loans": []}

    call_context = build_call_context(
        customer_id=customer_id,
        customer_record=customer_context,
        call_mode=call_mode,
        outbound_reason=outbound_reason,
        language=language_hint,
    )
    logger.info(
        "[REALTIME] Job started room=%s customer_id=%s call_mode=%s outbound_reason=%s language=%s",
        ctx.room.name, call_context.customer_id, call_context.call_mode,
        call_context.outbound_reason, call_context.language,
    )

    agent_cls = OutboundLoanMateAgent if call_context.call_mode == "outbound" else InboundLoanMateAgent
    agent = agent_cls(call_context, customer_context, session_id)

    realtime_kwargs: dict = dict(
        model=REALTIME_MODEL,
        api_key=settings.GOOGLE_API_KEY,
        voice="Puck",
        input_audio_transcription=genai_types.AudioTranscriptionConfig(),
        output_audio_transcription=genai_types.AudioTranscriptionConfig(),
    )
    if call_context.gemini_language_code:
        realtime_kwargs["language"] = call_context.gemini_language_code

    session = AgentSession(llm=RealtimeModel(**realtime_kwargs))

    @session.on("agent_state_changed")
    def _on_agent_state(ev):
        logger.info("[REALTIME] agent_state=%s", ev.new_state)

    @session.on("user_state_changed")
    def _on_user_state(ev):
        logger.info("[REALTIME] user_state=%s", ev.new_state)

    @session.on("function_tools_executed")
    def _on_tools_executed(ev):
        for call, output in zip(ev.function_calls, ev.function_call_outputs):
            logger.info("[TOOL] %s -> %s", call.name, str(output.output)[:120])

    @session.on("close")
    def _on_close(ev):
        logger.info(
            "[REALTIME] Session closed after %.0fms (reason=%s)",
            (time.monotonic() - t_job_start) * 1000, ev.reason,
        )

    # record=False: LiveKit Cloud's server-side "enable_recording" default
    # triggers a native access-violation crash in livekit-agents' recorder
    # audio-resampler thread on this machine (see docs — a
    # livekit-agents/livekit-rtc bug, unrelated to and discovered while
    # testing the RAG tool below). This project has no requirement to
    # record calls, so recording is explicitly disabled rather than
    # worked around.
    await session.start(
        agent=agent, room=ctx.room, room_input_options=RoomInputOptions(), record=False
    )
    logger.info("[REALTIME LATENCY] session_start: %.0fms", (time.monotonic() - t_job_start) * 1000)

    if call_context.call_mode == "outbound":
        greeting = build_outbound_instructions(call_context)
    else:
        greeting = build_inbound_instructions(call_context)
    session.generate_reply(instructions=greeting)


def run_worker() -> None:
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME))


if __name__ == "__main__":
    run_worker()
