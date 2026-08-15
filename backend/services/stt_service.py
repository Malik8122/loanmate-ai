"""
Speech-to-Text service.

Uses faster-whisper for local, offline transcription.
"""

from __future__ import annotations
import io
import os
import tempfile
import logging

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

logger = logging.getLogger(__name__)


class STTService:
    """Speech-to-Text abstraction layer."""

    def __init__(self, model_size: str = "base"):
        self.model_size = model_size
        self.model = None
        # Lazy load model so it doesn't block startup or crash if missing
        if WhisperModel is not None:
            try:
                # CPU execution for compatibility.
                # Compute type int8 for speed on CPU.
                self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            except Exception as e:
                logger.error(f"Failed to load WhisperModel: {e}")

    async def transcribe(self, audio_bytes: bytes, language: str = "auto") -> str:
        """Convert audio bytes to text.

        Args:
            audio_bytes: Raw audio data (WAV / OGG / WebM).
            language: BCP-47 language code, e.g. "en", "hi", or "auto".

        Returns:
            Transcribed text string.
        """
        if not audio_bytes:
            return ""

        if not self.model:
            return "[STT Error: Whisper model not loaded]"

        # Faster-whisper generally expects a file path or a file-like object.
        # Streamlit mic recorder outputs WAV (usually), which we can save to a temp file.
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            try:
                # If auto, let whisper detect. Otherwise force language
                kwargs = {}
                if language != "auto":
                    kwargs["language"] = language

                segments, info = self.model.transcribe(tmp_path, beam_size=5, **kwargs)
                
                text = " ".join([segment.text for segment in segments]).strip()
                return text
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                    
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return ""
