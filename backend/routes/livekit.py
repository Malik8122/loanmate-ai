"""
LiveKit Routes.

Endpoints:
    GET /api/livekit/token  — generate a connection token for the Streamlit UI
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
import logging

from backend.services.livekit_service import LiveKitService
from backend.services.loan_service import LoanService
from backend.services.agent_manager import agent_manager
from backend.services.call_transcript_store import CallTranscriptStore

logger = logging.getLogger(__name__)

router = APIRouter()
_livekit_service = LiveKitService()


def _room_name(customer_id: str, session_id: str) -> str:
    """One LiveKit room per conversation, not per customer — so two tabs/calls
    for the same demo customer never collide in the same room.
    """
    return f"{customer_id}-{session_id}"


class TokenResponse(BaseModel):
    token: str
    room_name: str
    url: str


class StatusResponse(BaseModel):
    configured: bool
    url_configured: bool
    credentials_configured: bool


class AgentActionResponse(BaseModel):
    room_name: str
    running: bool


class TranscriptEntry(BaseModel):
    role: str
    text: str


class TranscriptResponse(BaseModel):
    entries: list[TranscriptEntry]


@router.get("/status", response_model=StatusResponse)
async def get_status():
    """Report whether LiveKit credentials are configured on the backend.

    Never returns the actual URL/key/secret values — booleans only.
    """
    return StatusResponse(
        configured=_livekit_service.configured,
        url_configured=_livekit_service.url_configured,
        credentials_configured=_livekit_service.credentials_configured,
    )


@router.get("/token", response_model=TokenResponse)
async def get_token(
    customer_id: str = Query(..., description="The customer ID, used as the room name"),
    session_id: str = Query(..., description="The session ID, used as the participant identity")
):
    """Generate a LiveKit access token for the given customer."""
    logger.info("[LIVEKIT] Token request received — customer_id=%s", customer_id)
    logger.info(
        "[LIVEKIT] Credentials configured: url=%s key/secret=%s",
        "YES" if _livekit_service.url_configured else "NO",
        "YES" if _livekit_service.credentials_configured else "NO",
    )

    # Verify customer exists in mock data
    customer_data = LoanService.get_customer_with_loans(customer_id)
    if not customer_data:
        logger.warning("[LIVEKIT] Token request rejected — unknown customer_id=%s", customer_id)
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

    try:
        room_name = _room_name(customer_id, session_id)
        identity = f"loanmate-user-{customer_id}-{session_id}"
        token = _livekit_service.generate_token(room_name=room_name, participant_identity=identity)
        logger.info(
            "[LIVEKIT] Token generated successfully — room=%s identity=%s token_length=%d",
            room_name, identity, len(token),
        )
        return TokenResponse(
            token=token,
            room_name=room_name,
            url=_livekit_service.url
        )
    except RuntimeError as e:
        logger.error("[LIVEKIT] Configuration error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("[LIVEKIT] Failed to generate token: %s", e)
        raise HTTPException(status_code=500, detail="Failed to generate token.")


@router.post("/start-agent", response_model=AgentActionResponse)
async def start_agent(
    customer_id: str = Query(..., description="The customer ID"),
    session_id: str = Query(..., description="The session ID for conversation context"),
    call_direction: str = Query("inbound", pattern="^(inbound|outbound)$", description="'inbound' = user called LoanMate; 'outbound' = LoanMate calls the user and speaks first"),
):
    """Ensure the AI voice agent is connected to this conversation's LiveKit room.

    Idempotent: calling this while the agent is already in the room is a no-op.
    """
    if not _livekit_service.configured:
        raise HTTPException(status_code=500, detail="LiveKit is not configured on the server.")

    customer_data = LoanService.get_customer_with_loans(customer_id)
    if not customer_data:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

    room_name = _room_name(customer_id, session_id)
    agent_manager.start(room_name=room_name, customer_id=customer_id, session_id=session_id, call_direction=call_direction)
    return AgentActionResponse(room_name=room_name, running=agent_manager.is_running(room_name))


@router.post("/stop-agent", response_model=AgentActionResponse)
async def stop_agent(
    customer_id: str = Query(..., description="The customer ID"),
    session_id: str = Query(..., description="The session ID of the conversation to end"),
):
    """Disconnect the AI voice agent from this conversation's LiveKit room, ending the call."""
    room_name = _room_name(customer_id, session_id)
    agent_manager.stop(room_name=room_name)
    return AgentActionResponse(room_name=room_name, running=agent_manager.is_running(room_name))


@router.get("/transcript", response_model=TranscriptResponse)
async def get_transcript(
    session_id: str = Query(..., description="The session ID used for the call"),
):
    """Fetch and clear the buffered transcript for a call session.

    Called once, right after the call ends, so the voice conversation the
    agent had gets appended into the same chat history as text messages.
    """
    entries = CallTranscriptStore.get_and_clear(session_id)
    return TranscriptResponse(entries=[TranscriptEntry(**e) for e in entries])


@router.get("/transcript/peek", response_model=TranscriptResponse)
async def peek_transcript(
    session_id: str = Query(..., description="The session ID used for the call"),
    since_index: int = Query(0, description="Return only entries from this index onward"),
):
    """Read the transcript so far WITHOUT clearing it — used by the live in-call
    transcript view, which polls repeatedly while the call is still active.
    """
    entries = CallTranscriptStore.peek(session_id, since_index)
    return TranscriptResponse(entries=[TranscriptEntry(**e) for e in entries])
