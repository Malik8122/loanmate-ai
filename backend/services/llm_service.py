"""
LLM conversation service.

This module will manage the conversation with the LLM (e.g. Gemini)
including prompt construction, context management, and response parsing.
"""

from __future__ import annotations


class LLMService:
    """LLM conversation abstraction layer."""

    def __init__(self, model_name: str = "gemini-2.0-flash"):
        self.model_name = model_name
        self._conversation_history: list[dict] = []

    async def generate_response(
        self,
        user_message: str,
        customer_context: dict | None = None,
        language: str = "en",
    ) -> str:
        """Generate a conversational response from the LLM.

        Args:
            user_message: The user's query text.
            customer_context: Dict with customer/loan data to ground the response.
            language: Preferred response language.

        Returns:
            The assistant's reply text.
        """
        # TODO: Integrate actual LLM provider (Gemini / OpenAI)
        return (
            f"[LLM placeholder] I received your message: '{user_message}'. "
            "Once integrated, I will provide real loan/EMI answers."
        )

    def reset_conversation(self) -> None:
        """Clear conversation history for a new session."""
        self._conversation_history.clear()
