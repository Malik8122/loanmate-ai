"""
Twilio telephony service.

Handles Twilio-specific operations: outbound call initiation, TwiML generation,
and credential management.  All LLM/STT/TTS logic lives elsewhere.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.config import settings

try:
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
    HAS_TWILIO = True
except ImportError:
    TwilioClient = None  # type: ignore
    VoiceResponse = None  # type: ignore
    HAS_TWILIO = False

logger = logging.getLogger(__name__)


class TwilioService:
    """Thin wrapper around the Twilio REST API and TwiML generation."""

    def __init__(self):
        self.account_sid = settings.TWILIO_ACCOUNT_SID
        self.auth_token = settings.TWILIO_AUTH_TOKEN
        self.phone_number = settings.TWILIO_PHONE_NUMBER
        self.public_base_url = settings.PUBLIC_BASE_URL.rstrip("/") if settings.PUBLIC_BASE_URL else ""
        self.configured = bool(
            HAS_TWILIO
            and self.account_sid
            and self.auth_token
            and self.phone_number
        )
        self._client: TwilioClient | None = None
        if self.configured:
            self._client = TwilioClient(self.account_sid, self.auth_token)

    # ------------------------------------------------------------------
    # Outbound call
    # ------------------------------------------------------------------

    def initiate_call(self, to_number: str, customer_id: str) -> dict[str, Any]:
        """Place an outbound call via Twilio.

        Args:
            to_number: E.164 phone number to call.
            customer_id: The BFSI customer ID (passed to the answer URL).

        Returns:
            Dict with ``call_sid`` and ``status``.

        Raises:
            RuntimeError: If Twilio is not configured.
        """
        if not self.configured or not self._client:
            raise RuntimeError(
                "Twilio is not configured. "
                "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER in .env"
            )

        if not self.public_base_url:
            raise RuntimeError(
                "PUBLIC_BASE_URL is not set. "
                "Twilio needs a publicly reachable URL to send call events to."
            )

        answer_url = f"{self.public_base_url}/api/twilio/answer?customer_id={customer_id}"

        call = self._client.calls.create(
            to=to_number,
            from_=self.phone_number,
            url=answer_url,
            method="POST",
        )

        logger.info("Outbound call initiated — SID: %s, to: %s", call.sid, to_number)

        return {
            "call_sid": call.sid,
            "status": call.status,
        }

    # ------------------------------------------------------------------
    # TwiML helpers
    # ------------------------------------------------------------------

    def build_stream_twiml(self, customer_id: str = "CUST001") -> str:
        """Generate TwiML that starts a bidirectional media stream.

        Args:
            customer_id: Passed as a custom parameter inside the stream so the
                         WebSocket handler knows which customer is on the line.

        Returns:
            XML string suitable for an HTTP response to Twilio.
        """
        if not self.public_base_url:
            raise RuntimeError("PUBLIC_BASE_URL is not set.")

        # Convert http(s):// → ws(s)://
        ws_url = self.public_base_url.replace("https://", "wss://").replace("http://", "ws://")
        stream_url = f"{ws_url}/api/twilio/stream"

        response = VoiceResponse()

        # Greet the caller while the stream connects
        response.say(
            "Namaste! Unity Bank mein aapka swagat hai. Main aapka virtual assistant hoon. "
            "Aap apna sawaal pooch sakte hain.",
            voice="Polly.Aditi",
            language="hi-IN",
        )
        response.pause(length=1)

        # Start bidirectional media stream
        connect = Connect()
        stream = Stream(url=stream_url)
        stream.parameter(name="customer_id", value=customer_id)
        connect.append(stream)
        response.append(connect)

        return str(response)
