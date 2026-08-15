"""
Voice orchestration service.

Connects the three pipeline stages:  STT → LLM → TTS
"""

from __future__ import annotations

from backend.services.stt_service import STTService
from backend.services.llm_service import LLMService
from backend.services.tts_service import TTSService


class VoiceService:
    """End-to-end voice pipeline orchestrator."""

    def __init__(self):
        self.stt = STTService()
        self.llm = LLMService()
        self.tts = TTSService()

    async def handle_audio(
        self,
        audio_bytes: bytes,
        customer_context: dict | None = None,
        language: str = "en",
        session_id: str = "default",
    ) -> dict:
        """Full voice pipeline: audio in → text response + audio out.

        Args:
            audio_bytes: Raw audio from the user.
            customer_context: Customer/loan data for grounding.
            language: BCP-47 language code.
            session_id: The conversation session ID.

        Returns:
            Dict with keys ``reply_text``, ``reply_audio``, ``intent``, ``escalate``.
        """
        # Step 1: Speech-to-Text
        transcript = await self.stt.transcribe(audio_bytes, language)

        # Step 2: LLM
        llm_response = await self.llm.generate_response(
            user_message=transcript,
            customer_context=customer_context,
            language=language,
            session_id=session_id
        )
        reply_text = llm_response["reply"]

        # Step 3: Text-to-Speech
        reply_audio = await self.tts.synthesize(reply_text, language)

        return {
            "reply_text": reply_text,
            "reply_audio": reply_audio,
            "intent": llm_response.get("intent", "other"),
            "escalate": llm_response.get("escalate", False),
            "collected_application_data": llm_response.get("collected_application_data", {})
        }

    async def handle_text(
        self,
        text: str,
        customer_context: dict | None = None,
        language: str = "en",
        session_id: str = "default",
    ) -> dict:
        """Text-only pipeline (skip STT).

        Args:
            text: User's typed query.
            customer_context: Customer/loan data for grounding.
            language: BCP-47 language code.
            session_id: The conversation session ID.

        Returns:
            Dict with keys ``reply_text``, ``reply_audio``, ``intent``, ``escalate``.
        """
        llm_response = await self.llm.generate_response(
            user_message=text,
            customer_context=customer_context,
            language=language,
            session_id=session_id
        )
        reply_text = llm_response["reply"]
        
        reply_audio = await self.tts.synthesize(reply_text, language)

        return {
            "reply_text": reply_text,
            "reply_audio": reply_audio,
            "intent": llm_response.get("intent", "other"),
            "escalate": llm_response.get("escalate", False),
            "collected_application_data": llm_response.get("collected_application_data", {})
        }
