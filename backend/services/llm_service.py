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
            return self._fallback_response(user_message, language)

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

    def _fallback_response(self, user_message: str, language: str) -> dict[str, Any]:
        """Simple rule-based fallback when Gemini is not available."""
        msg_lower = user_message.lower()
        intent = "other"
        escalate = False
        reply = "[Fallback Mode] I received your message. Please add a valid GOOGLE_API_KEY to .env to enable AI responses."
        
        if "emi" in msg_lower:
            intent = "emi_query"
            reply = "[Fallback] Your current EMI information should be checked via the dashboard."
        elif "outstanding" in msg_lower:
            intent = "outstanding"
            reply = "[Fallback] Outstanding balance details will be shown soon."
        elif "apply" in msg_lower or "chahiye" in msg_lower:
            intent = "apply_loan"
            reply = "[Fallback] You want to apply for a loan. Our specialist will contact you."
        elif "agent" in msg_lower or "human" in msg_lower:
            intent = "escalate"
            escalate = True
            reply = "[Fallback] Transferring you to a human agent..."

        if language == "hi":
             reply = f"[Fallback Hindi] Aapka message mila: {user_message}. AI ke liye API key configure karein."

        return {
            "reply": reply,
            "intent": intent,
            "escalate": escalate,
            "collected_application_data": {}
        }
