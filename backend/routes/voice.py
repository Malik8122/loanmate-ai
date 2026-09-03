"""
Voice-interaction API routes.
"""

import base64

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel

from backend.models.schemas import TextQueryRequest, AssistantResponse
from backend.services.voice_service import VoiceService
from backend.services.loan_service import LoanService

router = APIRouter()
_voice_service = VoiceService()


class TTSRequest(BaseModel):
    text: str
    language: str = "en"


class TTSResponse(BaseModel):
    audio_base64: str | None = None


@router.post("/query/text", response_model=AssistantResponse)
async def text_query(request: TextQueryRequest):
    """Accept a text query and return the assistant's response.

    This endpoint is wired to the LLM.
    """
    customer_context = LoanService.get_customer_with_loans(request.customer_id)
    
    result = await _voice_service.handle_text(
        text=request.text,
        customer_context=customer_context,
        language=request.language,
        session_id=request.session_id,
    )
    
    return AssistantResponse(
        reply_text=result["reply_text"],
        audio_base64=result.get("reply_audio_b64"),
        language=request.language,
        intent=result["intent"],
        escalate=result["escalate"],
        session_id=request.session_id,
        transcribed_text=result.get("transcribed_text")
    )


@router.post("/query/audio", response_model=AssistantResponse)
async def audio_query(
    customer_id: str = Form(...),
    language: str = Form("en"),
    session_id: str = Form("default"),
    audio: UploadFile = File(...),
):
    """Accept an audio file and return the assistant's spoken response.

    This endpoint will later be wired to: STT → LLM → TTS.
    """
    audio_bytes = await audio.read()
    
    customer_context = LoanService.get_customer_with_loans(customer_id)
    
    result = await _voice_service.handle_audio(
        audio_bytes=audio_bytes,
        customer_context=customer_context,
        language=language,
        session_id=session_id
    )
    
    return AssistantResponse(
        reply_text=result["reply_text"],
        audio_base64=result.get("reply_audio_b64"),
        language=language,
        intent=result["intent"],
        escalate=result["escalate"],
        session_id=session_id,
        transcribed_text=result.get("transcribed_text")
    )


@router.post("/tts", response_model=TTSResponse)
async def synthesize_speech(request: TTSRequest):
    """Synthesize speech for a given piece of text without invoking the LLM.

    Used to speak scripted lines (e.g. a call's opening greeting) through the
    existing TTS pipeline.
    """
    audio_bytes = await _voice_service.tts.synthesize(request.text, request.language)
    return TTSResponse(
        audio_base64=base64.b64encode(audio_bytes).decode("utf-8") if audio_bytes else None
    )
