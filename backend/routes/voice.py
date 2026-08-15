"""
Voice-interaction API routes.
"""

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel

from backend.models.schemas import TextQueryRequest, AssistantResponse
from backend.services.voice_service import VoiceService
from backend.services.loan_service import LoanService

router = APIRouter()
_voice_service = VoiceService()


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
        language=request.language,
        intent=result["intent"],
        escalate=result["escalate"],
        session_id=request.session_id,
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
        language=language,
        intent=result["intent"],
        escalate=result["escalate"],
        session_id=session_id,
    )
