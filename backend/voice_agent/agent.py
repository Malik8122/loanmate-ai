"""
LiveKit Voice Agent using core WebRTC SDK.

This agent connects to a LiveKit room, subscribes to the user's microphone,
applies simple RMS-based Voice Activity Detection (VAD), and runs the
STT -> LLM -> TTS pipeline, sending audio back to the room.
"""

import asyncio
import base64
import io
import json
import logging
import uuid
import struct
import audioop

from livekit import rtc
from backend.config import settings
from backend.services.loan_service import LoanService
from backend.services.llm_service import LLMService
from backend.services.tts_service import TTSService
from backend.services.stt_service import STTService

logger = logging.getLogger(__name__)

# VAD parameters
_SILENCE_AMPLITUDE = 200
_SILENCE_THRESHOLD_MS = 800
_MIN_SPEECH_MS = 300


def _pcm16_to_wav(pcm_bytes: bytes, sample_rate: int = 48000, channels: int = 1) -> bytes:
    """Wrap raw PCM-16 bytes in a WAV header."""
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_bytes)

    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + data_size))
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))
    buf.write(struct.pack("<H", channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", byte_rate))
    buf.write(struct.pack("<H", block_align))
    buf.write(struct.pack("<H", bits_per_sample))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    buf.write(pcm_bytes)

    return buf.getvalue()


async def process_utterance(
    audio_buffer: bytes,
    customer_id: str,
    session_id: str,
    source: rtc.AudioSource,
    stt: STTService,
    llm: LLMService,
    tts: TTSService,
):
    """Run the pipeline on a chunk of audio and send back TTS output."""
    # Convert raw PCM (48kHz, 1 channel) from LiveKit to WAV for Whisper
    wav_bytes = _pcm16_to_wav(audio_buffer, sample_rate=48000)

    # STT
    transcript = await stt.transcribe(wav_bytes, language="auto")
    transcript = transcript.strip()
    if not transcript:
        return
        
    logger.info("Agent heard: %s", transcript)

    # LLM
    customer_context = LoanService.get_customer_with_loans(customer_id)
    llm_result = await llm.generate_response(
        user_message=transcript,
        customer_context=customer_context,
        language="auto",
        session_id=session_id,
    )
    reply_text = llm_result.get("reply", "")
    if not reply_text:
        return
        
    logger.info("Agent reply: %s", reply_text)

    # TTS
    tts_lang = "hi" if any("\u0900" <= c <= "\u097F" for c in reply_text) else "en"
    mp3_audio = await tts.synthesize(reply_text, tts_lang)
    if not mp3_audio:
        return

    # Convert MP3 to PCM for LiveKit AudioSource
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(mp3_audio))
        seg = seg.set_frame_rate(48000).set_channels(1).set_sample_width(2)
        pcm_bytes = seg.raw_data
    except Exception as e:
        logger.error("Failed to convert TTS MP3 to PCM: %s", e)
        return

    # Push to AudioSource
    # LiveKit AudioSource expects frames. The `capture_frame` takes an rtc.AudioFrame.
    # We create one from our PCM bytes.
    samples_per_channel = len(pcm_bytes) // 2
    frame = rtc.AudioFrame(
        data=pcm_bytes,
        sample_rate=48000,
        num_channels=1,
        samples_per_channel=samples_per_channel,
    )
    await source.capture_frame(frame)


async def run_voice_agent(room_name: str, customer_id: str, session_id: str):
    """
    Connects to a LiveKit room, listens for audio tracks, and responds.
    """
    if not settings.LIVEKIT_URL or not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        logger.error("LiveKit credentials not set. Cannot start agent.")
        return

    room = rtc.Room()
    
    stt = STTService(model_size="base")
    llm = LLMService()
    tts = TTSService()
    
    # We'll create a local audio track to push TTS audio
    source = rtc.AudioSource(48000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent-mic", source)
    options = rtc.TrackPublishOptions()
    options.source = rtc.TrackSource.SOURCE_MICROPHONE
    
    try:
        from backend.services.livekit_service import LiveKitService
        lk_service = LiveKitService()
        if not lk_service.configured:
            logger.error("LiveKit credentials not set. Cannot start agent.")
            return

        agent_token = lk_service.generate_token(room_name=room_name, participant_identity=f"agent-{session_id}")
        
        await room.connect(
            lk_service.url, 
            agent_token, 
            options=rtc.RoomOptions(auto_subscribe=True)
        )
        logger.info("Agent connected to room: %s", room_name)
        
        await room.local_participant.publish_track(track, options)

        @room.on("track_subscribed")
        def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info("Agent subscribed to audio track from %s", participant.identity)
                asyncio.create_task(handle_audio_track(track))

        async def handle_audio_track(audio_track: rtc.RemoteAudioTrack):
            stream = rtc.AudioStream(audio_track)
            audio_buffer = bytearray()
            silence_chunks = 0
            
            async for event in stream:
                # event.frame is an rtc.AudioFrame
                pcm_chunk = event.frame.data
                
                # Check RMS for VAD
                # frame.data is 16-bit PCM.
                rms = audioop.rms(pcm_chunk, 2)
                
                chunk_ms = (len(pcm_chunk) // 2) / 48  # sample rate 48000 -> 48 samples per ms
                
                if rms > _SILENCE_AMPLITUDE:
                    audio_buffer.extend(pcm_chunk)
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if len(audio_buffer) > 0:
                        audio_buffer.extend(pcm_chunk)
                        
                silence_ms = silence_chunks * chunk_ms
                speech_ms = (len(audio_buffer) // 2) / 48
                
                if len(audio_buffer) > 0 and silence_ms >= _SILENCE_THRESHOLD_MS and speech_ms >= _MIN_SPEECH_MS:
                    # Utterance complete
                    utterance = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    silence_chunks = 0
                    
                    # Process in background so we don't block the audio stream
                    asyncio.create_task(
                        process_utterance(
                            audio_buffer=utterance,
                            customer_id=customer_id,
                            session_id=session_id,
                            source=source,
                            stt=stt,
                            llm=llm,
                            tts=tts
                        )
                    )

        # Keep the connection alive as long as the room exists
        # In a real app we might disconnect when the user leaves. 
        # For the demo, we'll wait for a disconnect event or just run indefinitely.
        while room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
            await asyncio.sleep(1)
            
    except Exception as e:
        logger.error("Agent error: %s", e)
    finally:
        await room.disconnect()
