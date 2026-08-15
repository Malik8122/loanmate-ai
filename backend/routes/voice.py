"""
Voice-interaction API routes.
"""

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

router = APIRouter()


class TextQueryRequest(BaseModel):
    """Request body for a text-based voice-assistant query."""
    customer_id: str
    text: str
    language: str = "en"


class AssistantResponse(BaseModel):
    """Unified response returned by voice endpoints."""
    reply_text: str
    audio_base64: str | None = None
    language: str = "en"


@router.post("/query/text", response_model=AssistantResponse)
async def text_query(request: TextQueryRequest):
    """Accept a text query and return the assistant's response.

    This endpoint will later be wired to: LLM → TTS.
    """
    # Placeholder — echo confirmation until LLM service is connected
    return AssistantResponse(
        reply_text=f"[Placeholder] Received your query: '{request.text}'",
        language=request.language,
    )


@router.post("/query/audio", response_model=AssistantResponse)
async def audio_query(
    customer_id: str,
    language: str = "en",
    audio: UploadFile = File(...),
):
    """Accept an audio file and return the assistant's spoken response.

    This endpoint will later be wired to: STT → LLM → TTS.
    """
    audio_bytes = await audio.read()
    return AssistantResponse(
        reply_text=f"[Placeholder] Received {len(audio_bytes)} bytes of audio.",
        language=language,
    )
