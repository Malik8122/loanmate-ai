"""
Text-to-Speech service.

This module will wrap the chosen TTS provider (Google, ElevenLabs, etc.)
and expose a single async interface for converting text → audio.
"""

from __future__ import annotations


class TTSService:
    """Text-to-Speech abstraction layer."""

    def __init__(self, provider: str = "google"):
        self.provider = provider

    async def synthesize(self, text: str, language: str = "en") -> bytes:
        """Convert text to speech audio.

        Args:
            text: The text to speak.
            language: BCP-47 language code, e.g. "en", "hi".

        Returns:
            Audio bytes (WAV/MP3).
        """
        # TODO: Integrate actual TTS provider
        return b""
