"""
Speech-to-Text service.

This module will wrap the chosen STT provider (Google, Deepgram, etc.)
and expose a single async interface for converting audio → text.
"""

from __future__ import annotations


class STTService:
    """Speech-to-Text abstraction layer."""

    def __init__(self, provider: str = "google"):
        self.provider = provider

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> str:
        """Convert audio bytes to text.

        Args:
            audio_bytes: Raw audio data (WAV / OGG / WebM).
            language: BCP-47 language code, e.g. "en", "hi".

        Returns:
            Transcribed text string.
        """
        # TODO: Integrate actual STT provider
        return "[STT placeholder] Audio transcription will appear here."
