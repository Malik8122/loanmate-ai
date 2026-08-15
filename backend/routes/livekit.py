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

logger = logging.getLogger(__name__)

router = APIRouter()
_livekit_service = LiveKitService()


class TokenResponse(BaseModel):
    token: str
    room_name: str
    url: str


@router.get("/token", response_model=TokenResponse)
async def get_token(
    customer_id: str = Query(..., description="The customer ID, used as the room name"),
    session_id: str = Query(..., description="The session ID, used as the participant identity")
):
    """Generate a LiveKit access token for the given customer."""
    
    # Verify customer exists in mock data
    customer_data = LoanService.get_customer_with_loans(customer_id)
    if not customer_data:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")

    try:
        token = _livekit_service.generate_token(room_name=customer_id, participant_identity=session_id)
        return TokenResponse(
            token=token,
            room_name=customer_id,
            url=_livekit_service.url
        )
    except RuntimeError as e:
        logger.error(f"LiveKit configuration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate LiveKit token: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate token.")
