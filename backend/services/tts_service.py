"""
Text-to-Speech service.

Uses edge-tts for high-quality, open-source neural TTS.
"""

from __future__ import annotations
import logging
import io

try:
    import edge_tts
except ImportError:
    edge_tts = None

logger = logging.getLogger(__name__)


class TTSService:
    """Text-to-Speech abstraction layer."""

    def __init__(self):
        # Map languages to highly natural Neural voices
        # en-IN-NeerjaNeural and hi-IN-SwaraNeural are excellent for Indian context
        self.voice_map = {
            "en": "en-IN-NeerjaNeural",
            "hi": "hi-IN-SwaraNeural"
        }

    async def synthesize(self, text: str, language: str = "en") -> bytes:
        """Convert text to speech audio.

        Args:
            text: The text to speak.
            language: BCP-47 language code, e.g. "en", "hi".

        Returns:
            Audio bytes (MP3 format).
        """
        if not text:
            return b""

        if edge_tts is None:
            logger.error("edge-tts is not installed.")
            return b""
            
        # Default to English if language isn't matched
        voice = self.voice_map.get(language, self.voice_map["en"])

        try:
            communicate = edge_tts.Communicate(text, voice)
            audio_data = bytearray()
            
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])
                    
            return bytes(audio_data)
        except Exception as e:
            logger.error(f"TTS Synthesis failed: {e}")
            return b""
