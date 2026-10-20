"""
Realtime voice routes — the new primary voice path.

Unlike backend/routes/livekit.py (legacy path, which spawns an in-process
asyncio task running a custom STT/LLM/TTS loop for every room), this path
never touches the audio itself. It only issues a LiveKit access token whose
room configuration requests LiveKit's own agent dispatch: LiveKit Cloud
starts the registered "loanmate-realtime" worker (backend/voice_agent/
realtime_agent.py) in that room automatically. All realtime media,
turn-taking and interruption handling is LiveKit's and Gemini Live's, not
this backend's.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from livekit import api

from backend.services.livekit_service import LiveKitService
from backend.services.loan_service import LoanService
from backend.voice_agent.call_context import OUTBOUND_REASON_PATTERN, resolve_outbound_reason
from backend.voice_agent.realtime_agent import AGENT_NAME

logger = logging.getLogger(__name__)

router = APIRouter()
_livekit_service = LiveKitService()

_DEFAULT_CUSTOMER_ID = "CUST001"


def _room_name(customer_id: str, session_id: str) -> str:
    """Separate room namespace from the legacy path so the two voice
    pipelines never collide in the same room.
    """
    return f"realtime-{customer_id}-{session_id}"


class TokenResponse(BaseModel):
    token: str
    room_name: str
    url: str


@router.get("/token", response_model=TokenResponse)
async def get_token(
    session_id: str = Query(..., description="Per-call session id, used as room/participant identity"),
    customer_id: str = Query(_DEFAULT_CUSTOMER_ID, description="Demo customer id"),
    call_mode: str = Query("inbound", pattern="^(inbound|outbound)$", description="'inbound' = customer called LoanMate; 'outbound' = LoanMate is calling the customer"),
    outbound_reason: str | None = Query(None, pattern=OUTBOUND_REASON_PATTERN, description="Why LoanMate is calling (emi_reminder, overdue_followup, kyc_update, product_update, or auto to pick from the customer's account state) — ignored for inbound"),
    language: str = Query("english", pattern="^(english|hindi|hinglish)$", description="Preferred language pill selected in the UI — a hint, not a hard restriction"),
):
    """Issue a LiveKit token whose room configuration auto-dispatches the
    realtime LoanMate agent into the room as soon as the browser joins —
    no separate "start-agent" call needed for this path.

    The browser only ever supplies a customer_id to SELECT a demo customer;
    the actual customer record (name, loan) is resolved here from
    LoanService and carried to the agent as validated dispatch metadata —
    the agent never trusts customer identity fields from the client.
    """
    if not _livekit_service.configured:
        raise HTTPException(status_code=500, detail="LiveKit is not configured on the server.")

    customer_data = LoanService.get_customer_with_loans(customer_id)
    if not customer_data:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

    if call_mode == "outbound":
        outbound_reason = resolve_outbound_reason(customer_data, outbound_reason)
    else:
        outbound_reason = None

    room_name = _room_name(customer_id, session_id)
    identity = f"loanmate-user-{customer_id}-{session_id}"

    dispatch_metadata = json.dumps(
        {
            "customer_id": customer_id,
            "session_id": session_id,
            "call_mode": call_mode,
            "outbound_reason": outbound_reason,
            "language": language,
        }
    )

    token = (
        api.AccessToken(_livekit_service.api_key, _livekit_service.api_secret)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_room_config(
            api.RoomConfiguration(
                name=room_name,
                agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME, metadata=dispatch_metadata)],
            )
        )
    )
    logger.info(
        "[REALTIME] Token issued room=%s identity=%s call_mode=%s outbound_reason=%s",
        room_name, identity, call_mode, outbound_reason,
    )
    return TokenResponse(token=token.to_jwt(), room_name=room_name, url=_livekit_service.url)
