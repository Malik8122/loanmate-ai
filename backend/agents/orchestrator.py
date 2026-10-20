"""
Agent orchestrator: routes a user message to a deterministic banking
tool when the intent is clear, and only asks the LLM to narrate the
tool's output. Anything that doesn't map to a known tool (small talk,
open-ended questions, loan application chat) falls through to the
existing general-purpose LLM conversation.

    text -> detect language -> classify intent -> run tool (if any)
         -> LLM narrates tool result (or general LLM chat if no tool)

On a live call the direction changes what happens first (see
backend/agents/call_flow.py):

- inbound  — requests the bank must action (statement, NOC, complaint,
  human callback, ...) raise a service request with a reference number.
- outbound — LoanMate confirms it has the right person, delivers the
  campaign's purpose, and records the customer's response as the call
  outcome; only after that do free-form questions fall through to tools.

Plain text chat passes call_mode=None and skips both.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.agents import call_flow
from backend.agents.glossary import find_glossary_term, get_definition
from backend.agents.intent import classify_intent
from backend.agents.language import resolve_response_language
from backend.agents.nlu import parse_amount, parse_tenure_years
from backend.services import call_records
from backend.services.llm_service import LLMService
from backend.tools import calculator_tools, loan_tools

logger = logging.getLogger(__name__)

_DEFAULT_ELIGIBILITY_TENURE_MONTHS = 60
_DEFAULT_ELIGIBILITY_RATE = 10.0


class AgentOrchestrator:
    def __init__(self, llm: LLMService):
        self.llm = llm
        # Outbound call stage per session: "verify" -> "purpose" -> "done".
        self._outbound_stage: dict[str, str] = {}

    def start_outbound(self, session_id: str, reason: str, customer_context: dict | None, language: str) -> str:
        """Begin an outbound campaign call and return its opening line."""
        self._outbound_stage[session_id] = "verify"
        customer = (customer_context or {}).get("customer") or {}
        loan = self._campaign_loan(customer_context, reason)
        return call_flow.outbound_opener(reason, customer.get("name", "the customer"), (loan or {}).get("loan_type"), language)

    @staticmethod
    def _campaign_loan(customer_context: dict | None, reason: str | None) -> dict | None:
        loans = (customer_context or {}).get("loans") or []
        if reason == "overdue_followup":
            overdue = next((l for l in loans if l.get("loan_status") == "Overdue"), None)
            if overdue:
                return overdue
        return next((l for l in loans if l.get("loan_status") == "Active"), loans[0] if loans else None)

    async def handle(
        self,
        text: str,
        customer_context: dict | None,
        language: str,
        session_id: str,
        call_mode: str | None = None,
        outbound_reason: str | None = None,
    ) -> dict[str, Any]:
        detected_language = resolve_response_language(language, text)

        if call_mode == "outbound" and outbound_reason:
            scripted = self._handle_outbound(text, customer_context, detected_language, session_id, outbound_reason)
            if scripted:
                return scripted
        elif call_mode == "inbound":
            ticket = self._handle_inbound_request(text, customer_context, detected_language, session_id)
            if ticket:
                return ticket

        intent = classify_intent(text)
        trace = [f"Detected language: {detected_language}", f"Classified intent: {intent}"]
        logger.info("[INTENT] %s", intent)

        t0 = time.monotonic()
        tool_name, tool_result = self._run_tool(intent, text, customer_context, trace, detected_language)
        tool_ms = (time.monotonic() - t0) * 1000
        if tool_name and tool_name != "clarification_needed":
            logger.info("[TOOL] %s completed in %.1fms", tool_name, tool_ms)

        if tool_name == "clarification_needed":
            trace.append("Asking the user to clarify before calculating")
            return {
                "reply": tool_result["clarification"],
                "intent": intent,
                "escalate": False,
                "tool_used": None,
                "agent_trace": trace,
                "detected_language": detected_language,
            }

        if tool_result is None:
            trace.append("No matching tool — using general conversation")
            llm_response = await self.llm.generate_response(text, customer_context, detected_language, session_id)
            return {
                "reply": llm_response["reply"],
                "intent": llm_response.get("intent", intent),
                "escalate": llm_response.get("escalate", intent == "escalate"),
                "tool_used": None,
                "agent_trace": trace,
                "detected_language": detected_language,
            }

        trace.append(f"Tool executed: {tool_name}()")
        reply = await self.llm.phrase_tool_result(text, tool_result, detected_language, tool_name)
        trace.append("Response generated")

        return {
            "reply": reply,
            "intent": intent,
            "escalate": intent == "escalate",
            "tool_used": tool_name,
            "agent_trace": trace,
            "detected_language": detected_language,
        }

    # ------------------------------------------------------------------
    def _handle_inbound_request(
        self, text: str, customer_context: dict | None, language: str, session_id: str
    ) -> dict[str, Any] | None:
        request_type = call_flow.classify_service_request(text)
        if request_type is None and classify_intent(text) == "escalate":
            request_type = "human_callback"
        if request_type is None:
            return None
        customer_id = ((customer_context or {}).get("customer") or {}).get("customer_id", "unknown")
        record = call_records.raise_service_request(customer_id, request_type, details=text, session_id=session_id)
        reply = call_flow.service_request_reply(request_type, record["label"], record["reference"], language)
        return {
            "reply": reply,
            "intent": "escalate" if request_type == "human_callback" else "service_request",
            "escalate": request_type == "human_callback",
            "tool_used": "raise_service_request",
            "agent_trace": [
                f"Detected language: {language}",
                "Inbound call: service request detected",
                f"Tool executed: raise_service_request({request_type}) -> {record['reference']}",
            ],
            "detected_language": language,
        }

    def _handle_outbound(
        self, text: str, customer_context: dict | None, language: str, session_id: str, reason: str
    ) -> dict[str, Any] | None:
        stage = self._outbound_stage.get(session_id, "verify")
        if stage == "done":
            return None  # campaign finished — normal Q&A from here on

        customer = (customer_context or {}).get("customer") or {}
        customer_id = customer.get("customer_id", "unknown")
        trace = [f"Detected language: {language}", f"Outbound call ({reason}), stage: {stage}"]

        def _result(reply: str, tool: str | None = None) -> dict[str, Any]:
            return {
                "reply": reply,
                "intent": f"outbound_{reason}",
                "escalate": False,
                "tool_used": tool,
                "agent_trace": trace,
                "detected_language": language,
            }

        def _record(outcome: str) -> dict[str, Any]:
            amount = call_flow.promised_amount(text) if outcome == "promise_to_pay" else None
            call_records.record_call_outcome(
                customer_id, reason, outcome, promised_amount=amount, notes=text, session_id=session_id
            )
            self._outbound_stage[session_id] = "done"
            trace.append(f"Tool executed: record_call_outcome({outcome})")
            return _result(call_flow.outcome_reply(outcome, language), "record_call_outcome")

        if stage == "verify":
            # Busy / do-not-call / not-interested can come before confirming identity.
            early = call_flow.classify_outbound_response(text, reason, {"callback_requested", "do_not_call", "not_interested"})
            identity = call_flow.classify_identity_reply(text)
            if identity == "wrong_person" and early is None:
                trace.append("Right-party check failed — disclosing nothing")
                return _record("wrong_person")
            if early:
                return _record(early)
            if identity == "confirmed":
                self._outbound_stage[session_id] = "purpose"
                trace.append("Right party confirmed — stating purpose")
                loan = self._campaign_loan(customer_context, reason)
                first_name = (customer.get("name") or "").split(" ")[0]
                return _result(call_flow.purpose_message(reason, loan, first_name, language))
            trace.append("Identity unclear — asking again")
            return _result(call_flow.identity_retry(customer.get("name", "the customer"), language))

        allowed = call_records.OUTBOUND_OUTCOMES.get(reason, set())
        outcome = call_flow.classify_outbound_response(text, reason, allowed)
        if outcome:
            return _record(outcome)
        return None  # a question mid-campaign — answer it with the normal tools

    # ------------------------------------------------------------------
    def _run_tool(
        self, intent: str, text: str, customer_context: dict | None, trace: list[str], detected_language: str
    ) -> tuple[str | None, dict | None]:
        if intent == "emi_query":
            return "get_emi", {"emi": loan_tools.get_emi(customer_context)}
        if intent == "outstanding_query":
            return "get_outstanding_balance", {"outstanding": loan_tools.get_outstanding_balance(customer_context)}
        if intent == "emi_due_date":
            return "get_next_payment", {"due_date": loan_tools.get_next_payment(customer_context)}
        if intent == "remaining_emi":
            return "get_remaining_tenure", {"remaining_tenure_months": loan_tools.get_remaining_tenure(customer_context)}
        if intent == "loan_status":
            return "get_loan_status", {"status": loan_tools.get_loan_status(customer_context)}
        if intent == "payment_history":
            return "get_payment_history", loan_tools.get_payment_history(customer_context)
        if intent == "financial_glossary":
            term = find_glossary_term(text)
            definition = get_definition(term, detected_language) if term else None
            if not definition:
                return "clarification_needed", {
                    "clarification": "Which term would you like me to explain — for example EMI, prepayment, or foreclosure?"
                }
            return "get_glossary_definition", {"term": term, "definition": definition}
        if intent == "prepayment_simulation":
            return self._run_prepayment(text, customer_context, trace)
        if intent == "comparison":
            return self._run_comparison(text, customer_context, trace)
        if intent == "eligibility":
            trace.append("Eligibility check needs income/amount details not on file — asking user")
            return "clarification_needed", {
                "clarification": (
                    "To estimate eligibility I'll need your monthly income and the loan amount "
                    "you're considering — could you share those?"
                )
            }
        return None, None

    def _run_prepayment(
        self, text: str, customer_context: dict | None, trace: list[str]
    ) -> tuple[str, dict]:
        loan = loan_tools.get_loan_details(customer_context)
        if not loan:
            return "calculate_prepayment", {"error": "no_loan_found"}

        amount = parse_amount(text)
        if amount is None:
            trace.append("Prepayment amount not found in message — asking user")
            return "clarification_needed", {"clarification": "Sure — how much would you like to prepay?"}

        result = calculator_tools.calculate_prepayment(
            outstanding=loan["outstanding_amount"],
            annual_rate=loan["interest_rate"],
            remaining_months=loan["remaining_tenure"],
            prepayment_amount=amount,
        )
        result["prepayment_amount"] = amount
        result["loan_type"] = loan["loan_type"]
        return "calculate_prepayment", result

    def _run_comparison(
        self, text: str, customer_context: dict | None, trace: list[str]
    ) -> tuple[str, dict]:
        loan = loan_tools.get_loan_details(customer_context)
        if not loan:
            return "compare_tenures", {"error": "no_loan_found"}

        years = parse_tenure_years(text)
        if len(years) < 2:
            trace.append("Fewer than two tenure options found — asking user")
            return "clarification_needed", {
                "clarification": "Which tenures would you like me to compare — for example, 5 years vs 10 years?"
            }

        months = [y * 12 for y in years]
        comparison = calculator_tools.compare_tenures(loan["loan_amount"], loan["interest_rate"], months)
        return "compare_tenures", {"loan_type": loan["loan_type"], "comparison": comparison}
