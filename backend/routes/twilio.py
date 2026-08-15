"""
Twilio telephony routes.

Endpoints:
    POST /api/twilio/call       — initiate an outbound call to a mock customer
    POST /api/twilio/answer     — TwiML response that starts a bidirectional media stream
    WS   /api/twilio/stream     — WebSocket for the Twilio Media Stream
"""

from __future__ import annotations

import asyncio
import audioop
import base64
import io
import json
import logging
import struct
import tempfile
import os
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.services.twilio_service import TwilioService
from backend.services.loan_service import LoanService
from backend.services.llm_service import LLMService
from backend.services.tts_service import TTSService
from backend.services.stt_service import STTService

logger = logging.getLogger(__name__)

router = APIRouter()

_twilio_service = TwilioService()

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class OutboundCallRequest(BaseModel):
    customer_id: str


class OutboundCallResponse(BaseModel):
    call_sid: str
    status: str
    message: str


# ---------------------------------------------------------------------------
# POST /api/twilio/call — initiate outbound call
# ---------------------------------------------------------------------------

@router.post("/call", response_model=OutboundCallResponse)
async def initiate_call(request: OutboundCallRequest):
    """Initiate an outbound Twilio call to a mock customer."""

    # Look up customer phone number from mock data
    customer_data = LoanService.get_customer_with_loans(request.customer_id)
    if not customer_data:
        return OutboundCallResponse(
            call_sid="",
            status="error",
            message=f"Customer {request.customer_id} not found in mock data.",
        )

    phone = customer_data["customer"].get("phone", "")
    if not phone:
        return OutboundCallResponse(
            call_sid="",
            status="error",
            message=f"No phone number on file for customer {request.customer_id}.",
        )

    try:
        result = _twilio_service.initiate_call(
            to_number=phone,
            customer_id=request.customer_id,
        )
        return OutboundCallResponse(
            call_sid=result["call_sid"],
            status=result["status"],
            message="Call initiated successfully.",
        )
    except RuntimeError as exc:
        return OutboundCallResponse(
            call_sid="",
            status="configuration_error",
            message=str(exc),
        )
    except Exception as exc:
        logger.exception("Outbound call failed")
        return OutboundCallResponse(
            call_sid="",
            status="error",
            message=f"Call failed: {exc}",
        )


# ---------------------------------------------------------------------------
# POST /api/twilio/answer — return TwiML for bidirectional media stream
# ---------------------------------------------------------------------------

@router.post("/answer")
async def twilio_answer(request: Request, customer_id: str = Query("CUST001")):
    """Return TwiML that opens a bidirectional Twilio Media Stream."""
    try:
        twiml_xml = _twilio_service.build_stream_twiml(customer_id=customer_id)
    except RuntimeError as exc:
        # If PUBLIC_BASE_URL is missing we can't stream; fall back to a simple message
        from backend.services.twilio_service import VoiceResponse

        resp = VoiceResponse()
        resp.say("Sorry, the voice assistant is not available at this time. Please try again later.")
        twiml_xml = str(resp)
        logger.error("TwiML generation failed: %s", exc)

    return Response(content=twiml_xml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Helpers — audio conversion
# ---------------------------------------------------------------------------

def _mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert μ-law 8 kHz mono to linear PCM 16-bit 8 kHz mono."""
    return audioop.ulaw2lin(mulaw_bytes, 2)


def _pcm16_8k_to_wav(pcm_bytes: bytes, sample_rate: int = 8000, channels: int = 1) -> bytes:
    """Wrap raw PCM-16 bytes in a WAV header."""
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_bytes)

    buf = io.BytesIO()
    # RIFF header
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    # fmt chunk
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))            # chunk size
    buf.write(struct.pack("<H", 1))             # PCM format
    buf.write(struct.pack("<H", channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", bits_per_sample))
    # data chunk
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(pcm_bytes)

    return buf.getvalue()


def _mp3_to_mulaw_base64(mp3_bytes: bytes) -> str | None:
    """Convert MP3 audio (from edge-tts) to μ-law 8 kHz for Twilio playback.

    Uses pydub if available; returns None on failure so the caller can skip
    sending audio without crashing the call.
    """
    try:
        from pydub import AudioSegment

        seg = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        seg = seg.set_frame_rate(8000).set_channels(1).set_sample_width(2)

        pcm_bytes = seg.raw_data
        mulaw_bytes = audioop.lin2ulaw(pcm_bytes, 2)
        return base64.b64encode(mulaw_bytes).decode("ascii")
    except Exception as exc:
        logger.error("MP3 → μ-law conversion failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# WS /api/twilio/stream — Twilio bidirectional Media Stream
# ---------------------------------------------------------------------------

# Silence detection: if we accumulate >= SILENCE_THRESHOLD_MS of audio without
# meaningful volume we treat it as the end of the caller's utterance.
_CHUNK_MS = 20              # Twilio sends 20 ms chunks at 8 kHz μ-law
_SILENCE_THRESHOLD_MS = 800  # ~0.8 s of silence → flush
_SILENCE_AMPLITUDE = 200     # RMS below this is considered "silence"
_MIN_SPEECH_MS = 300         # ignore utterances shorter than this


@router.websocket("/stream")
async def twilio_stream(ws: WebSocket):
    """Handle the bidirectional Twilio Media Stream.

    Protocol overview:
        Twilio → server:  connected, start, media (base64 μ-law), stop
        server → Twilio:  media (base64 μ-law) for playback
    """
    await ws.accept()

    # Per-call state
    stream_sid: str = ""
    customer_id: str = "CUST001"
    session_id: str = str(uuid.uuid4())

    # Audio accumulator for VAD (Voice Activity Detection)
    audio_buffer = bytearray()
    silence_chunks = 0

    # Service instances (reuse the existing project services)
    stt = STTService(model_size="base")
    llm = LLMService()
    tts = TTSService()

    logger.info("Twilio WebSocket connection opened — session %s", session_id)

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")

            # ── connected ────────────────────────────────────────────
            if event == "connected":
                logger.info("Twilio stream connected: %s", msg.get("protocol"))

            # ── start ────────────────────────────────────────────────
            elif event == "start":
                start_data = msg.get("start", {})
                stream_sid = start_data.get("streamSid", "")
                custom_params = start_data.get("customParameters", {})
                customer_id = custom_params.get("customer_id", "CUST001")
                logger.info(
                    "Stream started — SID: %s, customer: %s",
                    stream_sid,
                    customer_id,
                )

            # ── media ────────────────────────────────────────────────
            elif event == "media":
                payload = msg.get("media", {}).get("payload", "")
                if not payload:
                    continue

                chunk = base64.b64decode(payload)       # μ-law bytes
                pcm_chunk = _mulaw_to_pcm16(chunk)      # PCM-16 for RMS

                rms = audioop.rms(pcm_chunk, 2)

                if rms > _SILENCE_AMPLITUDE:
                    # Speech detected
                    audio_buffer.extend(chunk)
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if len(audio_buffer) > 0:
                        audio_buffer.extend(chunk)  # include trailing silence

                # Check if utterance is complete (silence after speech)
                speech_ms = (len(audio_buffer) / 8) * _CHUNK_MS  # rough
                silence_ms = silence_chunks * _CHUNK_MS

                if (
                    len(audio_buffer) > 0
                    and silence_ms >= _SILENCE_THRESHOLD_MS
                    and speech_ms >= _MIN_SPEECH_MS
                ):
                    # ── Process the utterance ─────────────────────────
                    await _process_utterance(
                        ws=ws,
                        stream_sid=stream_sid,
                        audio_buffer=bytes(audio_buffer),
                        customer_id=customer_id,
                        session_id=session_id,
                        stt=stt,
                        llm=llm,
                        tts=tts,
                    )

                    # Reset accumulator
                    audio_buffer = bytearray()
                    silence_chunks = 0

            # ── stop ─────────────────────────────────────────────────
            elif event == "stop":
                logger.info("Twilio stream stopped — SID: %s", stream_sid)
                break

    except WebSocketDisconnect:
        logger.info("Twilio WebSocket disconnected — session %s", session_id)
    except Exception:
        logger.exception("Error in Twilio WebSocket handler")
    finally:
        try:
            await ws.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Utterance processing pipeline: STT → LLM → TTS → Twilio
# ---------------------------------------------------------------------------

async def _process_utterance(
    *,
    ws: WebSocket,
    stream_sid: str,
    audio_buffer: bytes,
    customer_id: str,
    session_id: str,
    stt: STTService,
    llm: LLMService,
    tts: TTSService,
) -> None:
    """Transcribe the caller's speech, get a reply, and send audio back."""

    # 1. μ-law → PCM WAV (what Whisper expects)
    pcm_bytes = _mulaw_to_pcm16(audio_buffer)
    wav_bytes = _pcm16_8k_to_wav(pcm_bytes, sample_rate=8000)

    # 2. Transcribe with Faster-Whisper
    transcript = await stt.transcribe(wav_bytes, language="auto")
    transcript = transcript.strip()

    if not transcript:
        logger.debug("Empty transcription — skipping")
        return

    logger.info("Caller said: %s", transcript)

    # 3. Get customer context from mock data
    customer_context = LoanService.get_customer_with_loans(customer_id)

    # 4. LLM response (uses existing generate_response + fallback)
    llm_result = await llm.generate_response(
        user_message=transcript,
        customer_context=customer_context,
        language="auto",
        session_id=session_id,
    )
    reply_text = llm_result.get("reply", "")

    if not reply_text:
        return

    logger.info("Assistant reply: %s", reply_text)

    # 5. TTS — generate MP3 via edge-tts
    # Detect Hindi script to pick the right voice
    tts_lang = "hi" if any("\u0900" <= c <= "\u097F" for c in reply_text) else "en"
    mp3_audio = await tts.synthesize(reply_text, tts_lang)

    if not mp3_audio:
        logger.warning("TTS returned empty audio")
        return

    # 6. Convert MP3 → μ-law base64 for Twilio
    mulaw_b64 = _mp3_to_mulaw_base64(mp3_audio)
    if not mulaw_b64:
        logger.warning("Audio conversion to μ-law failed — skipping playback")
        return

    # 7. Send audio back to Twilio via the Media Stream
    # Twilio expects 20 ms chunks of base64 μ-law at 8 kHz (160 bytes per chunk)
    CHUNK_SIZE = 160  # bytes of μ-law per 20 ms at 8 kHz
    raw_mulaw = base64.b64decode(mulaw_b64)

    for offset in range(0, len(raw_mulaw), CHUNK_SIZE):
        chunk = raw_mulaw[offset : offset + CHUNK_SIZE]
        chunk_b64 = base64.b64encode(chunk).decode("ascii")

        media_msg = json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {
                "payload": chunk_b64,
            },
        })

        try:
            await ws.send_text(media_msg)
        except Exception:
            logger.warning("Failed to send audio chunk to Twilio")
            return

    # Optional: send a mark event so Twilio notifies us when playback finishes
    mark_msg = json.dumps({
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": f"reply_{uuid.uuid4().hex[:8]}"},
    })
    try:
        await ws.send_text(mark_msg)
    except Exception:
        pass
