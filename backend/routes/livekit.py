"""
LiveKit Routes.

Endpoints:
    GET /api/livekit/token — generate a connection token for the browser client
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
import logging

from backend.services.livekit_service import LiveKitService

logger = logging.getLogger(__name__)

router = APIRouter()
_livekit_service = LiveKitService()


@router.get("/token", response_class=PlainTextResponse)
async def get_token(identity: str = "assistant_bot"):
    """Generate a LiveKit access token for the given participant identity."""
    try:
        token = _livekit_service.generate_token(room_name=identity, participant_identity=identity)
        return token
    except RuntimeError as e:
        logger.error(f"LiveKit configuration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to generate LiveKit token: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate token.")
