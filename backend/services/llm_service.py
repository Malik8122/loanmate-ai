"""
LLM conversation service.

This module will manage the conversation with the LLM (e.g. Gemini)
including prompt construction, context management, and response parsing.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.services.session_store import SessionStore
from backend.services.loan_service import LoanService

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

logger = logging.getLogger(__name__)

_PROMPTS_DIR = settings.PROMPTS_DIR
_SYSTEM_PROMPT_FILE = _PROMPTS_DIR / "system_prompt.txt"

# Tool names with a hand-written template in _template_phrase() below — for
# these, skip the Gemini narration call entirely (see phrase_tool_result).
_TEMPLATED_TOOL_NAMES = {
    "get_emi", "get_outstanding_balance", "get_next_payment", "get_remaining_tenure",
    "get_loan_status", "get_glossary_definition", "get_payment_history",
    "calculate_prepayment", "compare_tenures",
}

# retry=None disables the SDK's default retry-with-backoff on 429/503 — in a
# live voice call, a request that can't succeed quickly should fail fast and
# let the caller fall back, not silently retry for 20+ seconds of dead air.
# The explicit timeout is a second safety net against a slow-but-not-erroring
# response.
if HAS_GENAI:
    from google.generativeai.types import helper_types as _genai_helper_types
    _FAST_FAIL_REQUEST_OPTIONS = _genai_helper_types.RequestOptions(retry=None, timeout=8)
else:
    _FAST_FAIL_REQUEST_OPTIONS = None


class LLMService:
    """LLM conversation abstraction layer."""

    def __init__(self, model_name: str = settings.LLM_MODEL_NAME):
        self.model_name = model_name
        self.api_key = settings.GOOGLE_API_KEY
        self.has_key = bool(self.api_key and self.api_key.strip() != "your-google-api-key-here")
        
        if HAS_GENAI and self.has_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={"response_mime_type": "application/json"}
            )

    def _get_system_prompt(self, customer_context: dict | None = None) -> str:
        prompt_text = "You are a helpful banking assistant."
        if _SYSTEM_PROMPT_FILE.exists():
            with open(_SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
                prompt_text = f.read()

        loan_knowledge = LoanService.get_loan_knowledge()
        
        context_str = f"\n\n--- KNOWLEDGE BASE ---\n{json.dumps(loan_knowledge, indent=2)}\n"
        if customer_context:
            context_str += f"\n--- CUSTOMER CONTEXT ---\n{json.dumps(customer_context, indent=2)}\n"
        
        return prompt_text + context_str

    async def generate_response(
        self,
        user_message: str,
        customer_context: dict | None = None,
        language: str = "en",
        session_id: str = "default"
    ) -> dict[str, Any]:
        """Generate a conversational response from the LLM.

        Args:
            user_message: The user's query text.
            customer_context: Dict with customer/loan data to ground the response.
            language: Preferred response language.
            session_id: The conversation session ID.

        Returns:
            Dict containing reply, intent, and escalate flag.
        """
        history = SessionStore.get_or_create(session_id)

        # Fallback mechanism if no API key is provided
        if not (HAS_GENAI and self.has_key):
            return self._fallback_response(user_message, language, customer_context)

        system_instruction = self._get_system_prompt(customer_context)

        # We instantiate a new model instance here to pass the dynamic system_instruction
        # Alternatively we can manage chat sessions if the SDK version allows system_instruction in start_chat
        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_instruction,
                generation_config={"response_mime_type": "application/json"}
            )
            chat = model.start_chat(history=history)
            # send_message_async + retry=None + a short timeout: the sync
            # send_message() blocks the whole asyncio event loop for the entire
            # network round-trip (freezing LiveKit's own connection processing
            # during a live call), and the SDK's default retry policy will
            # silently retry a 429/503 with backoff for 20+ seconds — both are
            # unacceptable for a voice conversation, which needs to fail fast
            # and fall back rather than leave the user in dead air.
            response = await chat.send_message_async(
                user_message,
                request_options=_FAST_FAIL_REQUEST_OPTIONS,
            )
            
            # Update history with SDK's history
            SessionStore.get_or_create(session_id).clear()
            SessionStore.get_or_create(session_id).extend(chat.history)

            try:
                result = json.loads(response.text)
                return {
                    "reply": result.get("reply", "I'm sorry, I couldn't process that."),
                    "intent": result.get("intent", "other"),
                    "escalate": result.get("escalate", False),
                    "collected_application_data": result.get("collected_application_data", {})
                }
            except json.JSONDecodeError:
                logger.warning("Gemini returned non-JSON response, using fallback")
                return self._fallback_response(user_message, language, customer_context)
                
        except Exception as e:
            # Never speak a raw API exception to the user (especially over TTS in a
            # live call) — fall back to the deterministic/rule-based responder, which
            # still answers known loan questions correctly and gives a graceful
            # catch-all for general conversation.
            logger.error("Gemini generate_response failed, using fallback: %s", e)
            return self._fallback_response(user_message, language, customer_context)

    async def phrase_tool_result(
        self, user_message: str, tool_result: dict[str, Any], language: str, tool_name: str | None = None
    ) -> str:
        """Turn a deterministic tool's output into a natural-language reply.

        The model is given the exact computed numbers and told to narrate
        them, not recompute anything — this is what keeps every ₹ figure
        traceable to Python arithmetic instead of LLM guesswork.

        A deterministic tool answer never needs an LLM round-trip to be
        spoken naturally — every current tool already has a hand-written
        template below. Skipping Gemini here removes a full network+inference
        hop (several hundred ms to seconds) from the hottest path in the voice
        pipeline, and avoids burning API quota on a question with only one
        correct, already-known answer. Gemini is only invoked for a tool name
        that has no template yet (there currently are none).
        """
        if tool_name in _TEMPLATED_TOOL_NAMES or not (HAS_GENAI and self.has_key):
            return self._template_phrase(tool_result, language, tool_name)

        lang_label = {"hi": "Hindi/Hinglish", "en": "English"}.get(language, "English")
        prompt = (
            f"You are LoanMate AI, a banking voice assistant. "
            f"The user asked: \"{user_message}\"\n\n"
            f"A backend calculation already produced this exact result — use ONLY these numbers, "
            f"do not recompute or invent any figure:\n{json.dumps(tool_result, indent=2)}\n\n"
            f"Reply in {lang_label}, in 1-3 short conversational sentences, no markdown, "
            f"as if speaking the answer aloud. If the result contains an 'error' key, "
            f"apologise briefly and explain the information isn't available."
        )
        try:
            model = genai.GenerativeModel(model_name=self.model_name)
            response = await model.generate_content_async(prompt, request_options=_FAST_FAIL_REQUEST_OPTIONS)
            return response.text.strip()
        except Exception as e:
            logger.warning("phrase_tool_result: Gemini call failed, using template fallback: %s", e)
            return self._template_phrase(tool_result, language, tool_name)

    def _template_phrase(self, tool_result: dict[str, Any], language: str, tool_name: str | None) -> str:
        """Non-LLM fallback narration, used if Gemini is unavailable or errors.

        Mirrors the phrasing style of ``_fallback_response`` so the reply reads
        naturally even when this is the only path available (as it is whenever
        no Gemini API key is configured).
        """
        hi = language == "hi"

        if "error" in tool_result:
            return "Mujhe yeh jaankari abhi nahi mil paayi." if hi else "I couldn't retrieve that information right now."

        def inr(amount) -> str:
            try:
                return f"₹{int(amount):,}"
            except (TypeError, ValueError):
                return str(amount)

        if tool_name == "get_emi":
            emi = tool_result.get("emi")
            if emi is None:
                return "Aapke account mein koi active EMI nahi mila." if hi else "I couldn't find an active EMI on your account."
            return f"Aapki current monthly EMI {inr(emi)} hai." if hi else f"Your current monthly EMI is {inr(emi)}."

        if tool_name == "get_outstanding_balance":
            amt = tool_result.get("outstanding")
            if amt is None:
                return "Aapke account mein koi outstanding loan nahi mila." if hi else "I couldn't find an outstanding balance on your account."
            return f"Aapka outstanding balance {inr(amt)} hai." if hi else f"Your current outstanding balance is {inr(amt)}."

        if tool_name == "get_next_payment":
            due = tool_result.get("due_date")
            if not due:
                return "Aapki agli EMI ki date abhi available nahi hai." if hi else "Your next payment date isn't available right now."
            return f"Aapki agli EMI {due} ko due hai." if hi else f"Your next EMI is due on {due}."

        if tool_name == "get_remaining_tenure":
            months = tool_result.get("remaining_tenure_months")
            if months is None:
                return "Yeh jaankari abhi available nahi hai." if hi else "That information isn't available right now."
            return f"Aapke paas abhi {months} EMI baaki hain." if hi else f"You have {months} EMI(s) remaining."

        if tool_name == "get_loan_status":
            status = tool_result.get("status")
            if not status:
                return "Aapke account mein koi loan record nahi mila." if hi else "I couldn't find a loan record on your account."
            return f"Aapka loan abhi {status} status mein hai." if hi else f"Your loan is currently {status}."

        if tool_name == "get_glossary_definition":
            return tool_result.get("definition", "")

        if tool_name == "get_payment_history":
            return (
                "Detailed payment history is abhi available nahi hai, lekin aapka current schedule maujood hai."
                if hi
                else "Detailed past-payment history isn't available in this demo, but your current schedule is up to date."
            )

        if tool_name == "calculate_prepayment":
            if tool_result.get("loan_closed"):
                return (
                    "Itna prepay karne se aapka loan poora close ho jayega."
                    if hi
                    else "That prepayment amount would fully close out your loan."
                )
            reduction = inr(tool_result.get("emi_reduction", 0))
            new_emi = inr(tool_result.get("new_emi", 0))
            return (
                f"Is prepayment se aapki EMI {reduction} kam ho jayegi, nayi EMI {new_emi} hogi."
                if hi
                else f"That prepayment would lower your EMI by {reduction}, to a new EMI of {new_emi}."
            )

        if tool_name == "compare_tenures":
            rows = tool_result.get("comparison", [])
            summary = "; ".join(
                f"{r['tenure_months']//12}y: EMI {inr(r['emi'])}, interest {inr(r['total_interest'])}"
                for r in rows
            )
            return (
                f"Yeh raha comparison — {summary}."
                if hi
                else f"Here's the comparison — {summary}."
            )

        # Generic fallback for anything not specifically templated above.
        parts = [f"{k.replace('_', ' ')}: {v}" for k, v in tool_result.items() if v is not None]
        detail = "; ".join(parts) if parts else "no details available"
        return f"Yeh raha result: {detail}." if hi else f"Here's what I found: {detail}."

    def _fallback_response(
        self,
        user_message: str,
        language: str,
        customer_context: dict | None = None,
    ) -> dict[str, Any]:
        """Multilingual, data-driven rule-based fallback when Gemini is unavailable.

        Recognises EMI, outstanding, due-date, loan-status, and remaining-EMI
        queries in English, Hindi, and Hinglish and returns the real values from
        the customer's mock loan data.  No [Fallback] markers are shown to the
        customer — the response reads like a normal assistant reply.
        """
        import re

        msg_lower = user_message.lower().strip()
        intent = "other"
        escalate = False
        is_hindi_ish = language == "hi" or any(
            w in msg_lower for w in ["mera", "meri", "mujhe", "aap", "main", "kya", "hai"]
        )

        # ------------------------------------------------------------------
        # Extract loan data from customer_context if available.
        # For customers with multiple loans we report the *first active* loan;
        # if none is active we fall back to the first loan in the list.
        # ------------------------------------------------------------------
        loans: list[dict] = []
        customer_name: str = ""
        if customer_context:
            loans = customer_context.get("loans", [])
            cust = customer_context.get("customer", {})
            customer_name = cust.get("name", "")

        active_loans = [L for L in loans if L.get("loan_status", "").lower() == "active"]
        primary_loan: dict = active_loans[0] if active_loans else (loans[0] if loans else {})

        def _fmt_inr(amount: float | int) -> str:
            """Format a number as Indian-style currency string."""
            try:
                amount = int(amount)
            except (TypeError, ValueError):
                return str(amount)
            # Convert to Indian comma format: last 3 digits, then groups of 2
            s = str(amount)
            if len(s) <= 3:
                return f"₹{s}"
            last3 = s[-3:]
            rest = s[:-3]
            parts = []
            while len(rest) > 2:
                parts.insert(0, rest[-2:])
                rest = rest[:-2]
            if rest:
                parts.insert(0, rest)
            return "₹" + ",".join(parts) + "," + last3

        # ------------------------------------------------------------------
        # Intent detection — keywords cover English / Hindi / Hinglish
        # Order matters: check more specific patterns first.
        # ------------------------------------------------------------------

        # ── Due-date / Next EMI ──────────────────────────────────────────
        _due_keywords = [
            "next emi", "emi kab", "due date", "due kab", "kab hai",
            "kab bhari", "kab pay", "when is my emi", "when is the emi",
            "emi due", "kitne din", "due on",
        ]
        # ── Remaining EMIs / tenure ──────────────────────────────────────
        _remaining_keywords = [
            "remaining emi", "remaining tenure", "kitne emi", "kitni emi baki",
            "kitne emi baki", "emi baki", "bachi hai", "bache hain",
            "how many emi", "how many emis", "emi remaining", "tenure left",
            "mere kitne emi",
        ]
        # ── Loan status ──────────────────────────────────────────────────
        _status_keywords = [
            "loan status", "status kya", "loan kya hai", "mera loan",
            "loan active", "what is my loan", "loan ki sthiti",
        ]
        # ── Outstanding ──────────────────────────────────────────────────
        _outstanding_keywords = [
            "outstanding", "baki kitna", "baki amount", "due amount",
            "baqi", "pending amount", "total due", "kitna baki",
            "how much is my outstanding", "outstanding amount",
            "loan balance", "remaining balance",
        ]
        # ── EMI amount ───────────────────────────────────────────────────
        _emi_keywords = [
            "emi", "monthly payment", "monthly installment",
            "installment kitni", "emi kitni", "meri emi", "mera emi",
        ]
        # ── Escalation ───────────────────────────────────────────────────
        # Specific multi-word phrases only — bare "agent"/"help me" false-positive
        # on innocuous questions like "how can you help me?".
        _escalate_keywords = [
            "human agent", "talk to a human", "speak to a human", "speak with a human",
            "connect me to a human", "connect me to an agent", "talk to an agent",
            "speak to an agent", "real person", "loan officer", "customer care",
            "human se baat", "insaan se baat", "agent se connect", "agent se baat",
            "manager se baat",
        ]
        # ── Loan application ─────────────────────────────────────────────
        _apply_keywords = [
            "apply", "chahiye", "loan lena", "loan chahiye",
            "new loan", "naya loan",
        ]
        # ── Which bank ────────────────────────────────────────────────────
        _bank_keywords = [
            "which bank", "what bank", "kaunsa bank", "kaun sa bank",
            "bank ka naam", "naam kya hai is bank",
        ]
        # ── Assistant identity ──────────────────────────────────────────
        _identity_keywords = [
            "your name", "what is your name", "who are you",
            "aapka naam", "tumhara naam", "apka naam", "kaun ho tum", "aap kaun",
        ]
        # ── Assistant capabilities ───────────────────────────────────────
        _capability_keywords = [
            "what can you help", "what can you do", "how can you help",
            "how do you help", "aap kya kar sakte", "kya madad kar sakte",
            "aap kaise madad", "what all can you",
        ]

        def _any(keywords: list[str]) -> bool:
            return any(kw in msg_lower for kw in keywords)

        # ------------------------------------------------------------------
        # Name introduction — "My name is X" / "Mera naam X hai" etc.
        # Checked first since it's a distinct conversational turn, not a
        # banking-data query.
        # ------------------------------------------------------------------
        _name_patterns = [
            r"my name is ([a-zA-Z]+)",
            r"i am ([a-zA-Z]+)\b",
            r"i'm ([a-zA-Z]+)\b",
            r"this is ([a-zA-Z]+) speaking",
            r"mera naam ([a-zA-Z]+) hai",
            r"main ([a-zA-Z]+) hoon",
            r"mai ([a-zA-Z]+) hoon",
        ]
        _captured_name: str | None = None
        for pattern in _name_patterns:
            m = re.search(pattern, msg_lower)
            if m:
                _captured_name = m.group(1).capitalize()
                break

        # ------------------------------------------------------------------
        # Build reply
        # ------------------------------------------------------------------
        if _captured_name:
            intent = "greeting"
            reply = (
                f"Namaste {_captured_name} ji! Main aapki kis tarah madad kar sakta hoon — "
                f"EMI, loan status, ya outstanding balance ke baare mein?"
                if is_hindi_ish
                else f"Nice to meet you, {_captured_name}! How can I help you today — "
                f"EMI, loan status, outstanding balance, or something else?"
            )

        elif _any(_bank_keywords):
            intent = "general_info"
            reply = (
                "Aap Unity Bank se baat kar rahe hain."
                if is_hindi_ish
                else "You're speaking with Unity Bank."
            )

        elif _any(_identity_keywords):
            intent = "general_info"
            reply = (
                "Main aapka AI Loan aur EMI Assistant hoon, Unity Bank ki taraf se."
                if is_hindi_ish
                else "I'm your AI Loan & EMI Assistant here at Unity Bank."
            )

        elif _any(_capability_keywords):
            intent = "general_info"
            reply = (
                "Main aapki EMI, loan status, outstanding balance, due dates mein madad kar sakta hoon, "
                "naya loan apply karne mein bhi, aur zaroorat ho toh human agent se connect kar sakta hoon."
                if is_hindi_ish
                else "I can help you with EMI amounts, loan status, outstanding balances, due dates, "
                "applying for a new loan, or connecting you with a human agent if needed."
            )

        elif _any(_due_keywords):
            intent = "emi_due_date"
            if primary_loan:
                due = primary_loan.get("due_date") or "not available"
                loan_type = primary_loan.get("loan_type", "loan")
                reply = (
                    f"Aapki {loan_type} ki next EMI ki due date {due} hai."
                    if "kab" in msg_lower or language == "hi"
                    else f"Your next EMI for the {loan_type} is due on {due}."
                )
            else:
                reply = "Aapke account mein koi active loan nahi mila. Please branch se contact karein."

        elif _any(_remaining_keywords):
            intent = "remaining_emi"
            if primary_loan:
                remaining = primary_loan.get("remaining_tenure", "N/A")
                loan_type = primary_loan.get("loan_type", "loan")
                reply = (
                    f"Aapki {loan_type} mein abhi {remaining} EMI baaki hain."
                    if language == "hi" or any(w in msg_lower for w in ["kitne", "baki", "mere"])
                    else f"You have {remaining} EMI(s) remaining on your {loan_type}."
                )
            else:
                reply = "Aapke account mein koi active loan nahi mila."

        elif _any(_status_keywords):
            intent = "loan_status"
            if primary_loan:
                status = primary_loan.get("loan_status", "N/A")
                loan_type = primary_loan.get("loan_type", "loan")
                reply = (
                    f"Aapka {loan_type} abhi {status} status mein hai."
                    if language == "hi" or any(w in msg_lower for w in ["kya", "mera", "status"])
                    else f"Your {loan_type} is currently {status}."
                )
            else:
                reply = "Aapke account mein koi loan record nahi mila."

        elif _any(_outstanding_keywords):
            intent = "outstanding_query"
            if primary_loan:
                outstanding = primary_loan.get("outstanding_amount", 0)
                loan_type = primary_loan.get("loan_type", "loan")
                formatted = _fmt_inr(outstanding)
                reply = (
                    f"Aapka {loan_type} ka outstanding loan amount {formatted} hai."
                    if language == "hi" or any(w in msg_lower for w in ["mera", "kitna", "aapka", "outstanding"])
                    else f"Your current outstanding balance on the {loan_type} is {formatted}."
                )
            else:
                reply = "Aapke account mein koi outstanding loan nahi mila."

        elif _any(_emi_keywords):
            intent = "emi_query"
            if primary_loan:
                emi = primary_loan.get("emi", 0)
                loan_type = primary_loan.get("loan_type", "loan")
                formatted = _fmt_inr(emi)
                reply = (
                    f"Aapki {loan_type} ki current monthly EMI {formatted} hai."
                    if language == "hi" or any(w in msg_lower for w in ["meri", "mera", "kitni", "kitna"])
                    else f"Your current monthly EMI for the {loan_type} is {formatted}."
                )
            else:
                reply = "Aapke account mein koi active EMI nahi mila."

        elif _any(_escalate_keywords):
            intent = "escalate"
            escalate = True
            reply = "Aapko ek human agent se connect kar raha hoon. Ek moment please."

        elif _any(_apply_keywords):
            intent = "apply_loan"
            reply = (
                "Loan application ke liye, please hamare portal par jaayein ya branch visit karein. "
                "Aapka application jald process hoga."
            )

        else:
            reply = (
                "Mujhe samajh nahi aaya. Kya aap apna sawaal dobara pooch sakte hain? "
                "Main EMI, outstanding balance, loan status, aur due dates ke baare mein "
                "madad kar sakta hoon."
            )

        return {
            "reply": reply,
            "intent": intent,
            "escalate": escalate,
            "collected_application_data": {},
        }
