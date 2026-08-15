"""
LLM conversation service.

This module will manage the conversation with the LLM (e.g. Gemini)
including prompt construction, context management, and response parsing.
"""

from __future__ import annotations

import json
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

_PROMPTS_DIR = settings.PROMPTS_DIR
_SYSTEM_PROMPT_FILE = _PROMPTS_DIR / "system_prompt.txt"


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
            response = chat.send_message(user_message)
            
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
                return {
                    "reply": "I'm having trouble forming a proper response right now.",
                    "intent": "other",
                    "escalate": True,
                    "collected_application_data": {}
                }
                
        except Exception as e:
             return {
                "reply": f"An error occurred while connecting to the AI: {str(e)}",
                "intent": "other",
                "escalate": True,
                "collected_application_data": {}
            }

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
        msg_lower = user_message.lower().strip()
        intent = "other"
        escalate = False

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
        _escalate_keywords = [
            "agent", "human", "representative", "officer",
            "manager", "help me", "connect me",
        ]
        # ── Loan application ─────────────────────────────────────────────
        _apply_keywords = [
            "apply", "chahiye", "loan lena", "loan chahiye",
            "new loan", "naya loan",
        ]

        def _any(keywords: list[str]) -> bool:
            return any(kw in msg_lower for kw in keywords)

        # ------------------------------------------------------------------
        # Build reply
        # ------------------------------------------------------------------
        if _any(_due_keywords):
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
