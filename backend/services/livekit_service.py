"""
LiveKit Service.

Handles generating secure access tokens for the browser to connect to LiveKit.
"""

from __future__ import annotations
import logging
from backend.config import settings

try:
    from livekit import api
    HAS_LIVEKIT = True
except ImportError:
    HAS_LIVEKIT = False

logger = logging.getLogger(__name__)


class LiveKitService:
    def __init__(self):
        self.url = settings.LIVEKIT_URL
        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET
        self.configured = bool(HAS_LIVEKIT and self.url and self.api_key and self.api_secret)

    def generate_token(self, room_name: str, participant_identity: str) -> str:
        """Generate an access token for a frontend client to join the WebRTC room."""
        if not self.configured:
            raise RuntimeError(
                "LiveKit is not configured. "
                "Ensure LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET are set."
            )

        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(participant_identity)
            .with_name(participant_identity)
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                )
            )
        )
        return token.to_jwt()
