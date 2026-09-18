"""
Voice orchestration service.

Connects the three pipeline stages:  STT → LLM → TTS
"""

from __future__ import annotations
import base64
import logging

from backend.services.stt_service import STTService
from backend.services.llm_service import LLMService
from backend.services.tts_service import TTSService
from backend.agents.orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)

class VoiceService:
    """End-to-end voice pipeline orchestrator."""

    def __init__(self):
        # "tiny" benchmarked faster and more reliable for keyword-based intent
        # matching than "base" for this project's phrasing (see backend/voice_agent/agent.py).
        self.stt = STTService(model_size="tiny")
        self.llm = LLMService()
        self.tts = TTSService()
        self.agent = AgentOrchestrator(self.llm)

    async def handle_audio(
        self,
        audio_bytes: bytes,
        customer_context: dict | None = None,
        language: str = "auto",
        session_id: str = "default",
    ) -> dict:
        """Full voice pipeline: audio in → text response + audio out.

        Args:
            audio_bytes: Raw audio from the user.
            customer_context: Customer/loan data for grounding.
            language: BCP-47 language code (en, hi, or auto).
            session_id: The conversation session ID.

        Returns:
            Dict with keys ``reply_text``, ``reply_audio_b64``, ``intent``, ``escalate``, ``transcribed_text``.
        """
        # Step 1: Speech-to-Text
        transcript = ""
        if audio_bytes:
            transcript = await self.stt.transcribe(audio_bytes, language)
            
        if not transcript:
             # Handle empty/unclear audio gracefully
             reply_text = "I couldn't hear that clearly. Please try again."
             # Use "en" for default error voice if auto was passed
             tts_lang = "en" if language == "auto" else language
             reply_audio = await self.tts.synthesize(reply_text, tts_lang)
             return {
                 "reply_text": reply_text,
                 "reply_audio_b64": base64.b64encode(reply_audio).decode("utf-8") if reply_audio else None,
                 "intent": "other",
                 "escalate": False,
                 "transcribed_text": ""
             }

        # Step 2: Agent orchestrator (intent -> tool -> LLM narration, or general chat)
        agent_response = await self.agent.handle(
            text=transcript,
            customer_context=customer_context,
            language=language,
            session_id=session_id,
        )
        reply_text = agent_response["reply"]

        # Step 3: Text-to-Speech
        # If input was auto, output should try to match the recognized language from text.
        tts_lang = agent_response.get("detected_language") or language
        if tts_lang == "auto":
            # Simple heuristic: if devanagari characters exist, use Hindi
            if any("\u0900" <= c <= "\u097F" for c in reply_text):
                tts_lang = "hi"
            else:
                tts_lang = "en"

        reply_audio = await self.tts.synthesize(reply_text, tts_lang)

        return {
            "reply_text": reply_text,
            "reply_audio_b64": base64.b64encode(reply_audio).decode("utf-8") if reply_audio else None,
            "intent": agent_response.get("intent", "other"),
            "escalate": agent_response.get("escalate", False),
            "transcribed_text": transcript,
            "detected_language": agent_response.get("detected_language"),
            "tool_used": agent_response.get("tool_used"),
            "agent_trace": agent_response.get("agent_trace"),
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
            Dict with keys ``reply_text``, ``reply_audio_b64``, ``intent``, ``escalate``.
        """
        agent_response = await self.agent.handle(
            text=text,
            customer_context=customer_context,
            language=language,
            session_id=session_id,
        )
        reply_text = agent_response["reply"]

        tts_lang = agent_response.get("detected_language") or language
        if tts_lang == "auto":
            tts_lang = "hi" if any("ऀ" <= c <= "ॿ" for c in reply_text) else "en"

        reply_audio = await self.tts.synthesize(reply_text, tts_lang)

        return {
            "reply_text": reply_text,
            "reply_audio_b64": base64.b64encode(reply_audio).decode("utf-8") if reply_audio else None,
            "intent": agent_response.get("intent", "other"),
            "escalate": agent_response.get("escalate", False),
            "transcribed_text": text,
            "detected_language": agent_response.get("detected_language"),
            "tool_used": agent_response.get("tool_used"),
            "agent_trace": agent_response.get("agent_trace"),
        }
