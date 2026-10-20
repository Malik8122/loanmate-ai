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
import subprocess
import time
import uuid
import struct
import audioop

import imageio_ffmpeg
from livekit import rtc
from backend.config import settings
from backend.services.loan_service import LoanService
from backend.services.llm_service import LLMService
from backend.services.tts_service import TTSService
from backend.services.stt_service import STTService
from backend.services.call_transcript_store import CallTranscriptStore
from backend.agents.orchestrator import AgentOrchestrator

logger = logging.getLogger(__name__)

_FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

# VAD parameters.
#
# _SILENCE_AMPLITUDE is a FALLBACK floor, not the primary threshold: real
# microphone audio (processed by the browser's echo cancellation / noise
# suppression / AGC) has a completely different RMS profile than the clean
# synthetic TTS audio this was originally tuned against, and mic gain varies
# a lot across devices. The agent instead calibrates an ambient noise floor
# from the first _CALIBRATION_MS of audio after the track subscribes, and
# sets the actual speech threshold above that — falling back to the fixed
# floor only if calibration produces something unreasonably low.
# Measured the longest natural internal (mid-sentence) pause across every test
# phrase's synthesized audio using this exact RMS method: 130ms was the worst
# case (a comma pause in a reply sentence). That leaves a wide margin under
# 600ms — synthetic TTS speech is spoken briskly with minimal hesitation
# though, which real human speech (especially mid-thought in a second
# language) will not always match, so this isn't pushed all the way to the
# 500ms floor the brief allowed for. 600ms is the evidence-backed middle
# ground: meaningfully snappier than 700ms with headroom still intact for
# real hesitation. If real testing shows premature cutoffs, raise this back
# toward 700ms; the [VOICE] Speech ended log line reports the actual silence
# duration observed, which is exactly the number needed to retune this.
_SILENCE_AMPLITUDE = 150
_SILENCE_THRESHOLD_MS = 600
_MIN_SPEECH_MS = 250
_CALIBRATION_MS = 400
_NOISE_FLOOR_MULTIPLIER = 2.5


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


def _mp3_to_pcm16(mp3_bytes: bytes, sample_rate: int = 48000, channels: int = 1) -> bytes:
    """Decode MP3 bytes to raw PCM16 via the ffmpeg binary bundled by imageio-ffmpeg."""
    proc = subprocess.run(
        [
            _FFMPEG_EXE, "-hide_banner", "-loglevel", "error",
            "-i", "pipe:0",
            "-f", "s16le", "-ar", str(sample_rate), "-ac", str(channels),
            "pipe:1",
        ],
        input=mp3_bytes,
        capture_output=True,
        check=True,
    )
    return proc.stdout


async def _publish_state(room: rtc.Room, state: str) -> None:
    """Broadcast the agent's real pipeline state over LiveKit's data channel.

    The browser listens for these (RoomEvent.DataReceived) to show accurate
    Listening/Processing/Speaking labels \u2014 never a client-side timer guess.

    publish_data is a coroutine \u2014 this must be awaited, or the call silently
    creates a coroutine that never runs (no exception, nothing sent).
    """
    try:
        await room.local_participant.publish_data(
            json.dumps({"state": state}).encode("utf-8"), reliable=True
        )
        logger.info("[VOICE] State: %s", state)
    except Exception as e:
        logger.warning("[VOICE] Failed to publish state '%s': %s", state, e)


_FRAME_MS = 20  # 20ms frames @ 48kHz mono 16-bit = 1920 bytes/frame
_FRAME_BYTES = int(48000 * (_FRAME_MS / 1000) * 2)


async def _synthesize_and_publish(text: str, language: str, tts: TTSService, source: rtc.AudioSource) -> float | None:
    """Run text through TTS and push the resulting audio into the LiveKit track.

    Streamed as small (20ms) frames rather than one giant frame for the whole
    reply \u2014 this is what makes barge-in real rather than cosmetic. Handing the
    entire reply to capture_frame() in one call means all of it is already
    queued for transmission the instant this call returns, so cancelling the
    surrounding task afterwards can't stop any of it from playing. Chunking
    means a cancellation between chunks actually stops further audio from
    being sent (at most ~20ms already in flight).

    NOTE: this coroutine only *returns* once every chunk has been handed to
    capture_frame(), which paces to roughly real-time \u2014 so its total run time
    is close to the spoken length of the reply, not how long the user waited
    before hearing anything. Callers timing "how long until the user hears a
    response" should use the returned first-frame timestamp, not the time
    this function took to return.

    Returns the time.monotonic() timestamp of the first frame actually
    published, or None if nothing was published (any failure).
    """
    tts_start = time.monotonic()
    mp3_audio = await tts.synthesize(text, language)
    if not mp3_audio:
        logger.error("[TTS] Synthesis returned no audio")
        return None
    logger.info("[VOICE LATENCY] tts_synthesize: %.0fms (%d bytes mp3)", (time.monotonic() - tts_start) * 1000, len(mp3_audio))

    # Convert MP3 to raw PCM16 for the LiveKit AudioSource.
    # Shelling out to the bundled ffmpeg binary avoids a pydub/ffprobe dependency
    # that isn't available in this environment.
    convert_start = time.monotonic()
    try:
        pcm_bytes = await asyncio.to_thread(_mp3_to_pcm16, mp3_audio)
    except Exception as e:
        logger.error("Failed to convert TTS MP3 to PCM: %s", e)
        return None
    logger.info("[VOICE LATENCY] mp3_to_pcm: %.0fms", (time.monotonic() - convert_start) * 1000)

    frames_published = 0
    first_frame_ts = None
    try:
        for i in range(0, len(pcm_bytes), _FRAME_BYTES):
            chunk = pcm_bytes[i:i + _FRAME_BYTES]
            if len(chunk) < _FRAME_BYTES:
                chunk = chunk + b"\x00" * (_FRAME_BYTES - len(chunk))
            frame = rtc.AudioFrame(
                data=chunk,
                sample_rate=48000,
                num_channels=1,
                samples_per_channel=_FRAME_BYTES // 2,
            )
            await source.capture_frame(frame)
            if first_frame_ts is None:
                first_frame_ts = time.monotonic()
                logger.info("[VOICE LATENCY] tts_first_audio_frame: %.0fms after synth start", (first_frame_ts - tts_start) * 1000)
            frames_published += 1
    except asyncio.CancelledError:
        logger.info("[VOICE] Barge-in \u2014 stopped TTS playback after %d/%d frames", frames_published, (len(pcm_bytes) + _FRAME_BYTES - 1) // _FRAME_BYTES)
        raise

    logger.info("[VOICE] Audio published back to room: %d frames (%d bytes)", frames_published, len(pcm_bytes))
    return first_frame_ts


async def process_utterance(
    audio_buffer: bytes,
    customer_id: str,
    session_id: str,
    source: rtc.AudioSource,
    stt: STTService,
    agent: AgentOrchestrator,
    tts: TTSService,
    room: rtc.Room,
    speech_end_ts: float | None = None,
    call_direction: str = "inbound",
    outbound_reason: str | None = None,
):
    """Run the pipeline on a chunk of audio and send back TTS output.

    speech_end_ts (from time.monotonic()) marks the moment VAD decided the
    user stopped talking \u2014 every latency number below is measured from there,
    since that's the number that actually matters for how the call *feels*.
    """
    t_speech_end = speech_end_ts if speech_end_ts is not None else time.monotonic()
    await _publish_state(room, "processing")

    # Convert raw PCM (48kHz, 1 channel) from LiveKit to WAV for Whisper
    wav_bytes = _pcm16_to_wav(audio_buffer, sample_rate=48000)

    # STT
    t0 = time.monotonic()
    transcript = await stt.transcribe(wav_bytes, language="auto")
    stt_ms = (time.monotonic() - t0) * 1000
    transcript = transcript.strip()
    if not transcript:
        logger.info("[VOICE LATENCY] stt_final: %.0fms -> empty transcript, could not hear the user", stt_ms)
        await _publish_state(room, "listening")
        # Don't leave the user hanging on silence/noise that didn't transcribe \u2014
        # a real voice assistant says *something* rather than going quiet.
        await _publish_state(room, "speaking")
        await _synthesize_and_publish("Sorry, I couldn't hear that clearly. Could you say that again?", "en", tts, source)
        await _publish_state(room, "listening")
        return

    logger.info("[VOICE LATENCY] stt_final: %.0fms -> \"%s\"", stt_ms, transcript)
    CallTranscriptStore.append(session_id, "user", transcript)

    # Agent orchestrator: same intent -> tool -> narration pipeline the text chat uses,
    # so a voice call gets real EMI/prepayment/etc. answers, not just free-form chat.
    t0 = time.monotonic()
    customer_context = LoanService.get_customer_with_loans(customer_id)
    agent_result = await agent.handle(
        text=transcript,
        customer_context=customer_context,
        language="auto",
        session_id=session_id,
        call_mode=call_direction,
        outbound_reason=outbound_reason,
    )
    orchestrator_ms = (time.monotonic() - t0) * 1000
    tool_used = agent_result.get("tool_used")
    logger.info(
        "[VOICE LATENCY] orchestrator: %.0fms (lang=%s intent=%s tool=%s)",
        orchestrator_ms, agent_result.get("detected_language"), agent_result.get("intent"), tool_used or "none (LLM)",
    )

    reply_text = agent_result.get("reply", "")
    if not reply_text:
        await _publish_state(room, "listening")
        return

    logger.info("[AGENT] Reply: %s", reply_text)
    CallTranscriptStore.append(session_id, "assistant", reply_text)

    tts_lang = "hi" if any("\u0900" <= c <= "\u097F" for c in reply_text) else "en"
    await _publish_state(room, "speaking")
    first_frame_ts = await _synthesize_and_publish(reply_text, tts_lang, tts, source)
    if first_frame_ts is not None:
        # This is the number that actually matters for how the call *feels*:
        # speech_end -> the moment the user starts hearing something. It is
        # NOT the same as when _synthesize_and_publish() returns, since that
        # only happens once the whole reply has been paced out in real time.
        logger.info(
            "[VOICE LATENCY] TOTAL speech_end->first_audible_response: %.0fms (stt=%.0fms orchestrator=%.0fms tts_to_first_frame=%.0fms)",
            (first_frame_ts - t_speech_end) * 1000, stt_ms, orchestrator_ms,
            (first_frame_ts - t_speech_end) * 1000 - stt_ms - orchestrator_ms,
        )
    await _publish_state(room, "listening")


async def run_voice_agent(
    room_name: str,
    customer_id: str,
    session_id: str,
    call_direction: str = "inbound",
    outbound_reason: str | None = None,
):
    """
    Connects to a LiveKit room, listens for audio tracks, and responds.

    call_direction == "outbound" means LoanMate initiated the call (the demo
    "Bank is Calling You" flow) for one campaign purpose (outbound_reason):
    the agent speaks first with that purpose's opener, confirms it has the
    right person, and records a call outcome. "inbound" (default) just
    listens and serves whatever the customer asks for.
    """
    if not settings.LIVEKIT_URL or not settings.LIVEKIT_API_KEY or not settings.LIVEKIT_API_SECRET:
        logger.error("[VOICE] LiveKit credentials not set. Cannot start agent.")
        return

    room = rtc.Room()
    
    # "tiny" beats "base" on both axes for this use case: ~14% faster
    # transcription and ~61% faster model load in direct benchmarking, while
    # also preserving keyword triggers ("EMI", "prepay") more reliably --
    # "base" was observed switching to a different script entirely on one
    # Hindi/Hinglish test phrase, which would break keyword-based intent
    # matching outright. See PR/commit notes for the benchmark data.
    stt = STTService(model_size="tiny")
    llm = LLMService()
    agent = AgentOrchestrator(llm)
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
        logger.info("[VOICE] Agent connected to room: %s", room_name)
        await _publish_state(room, "connected")

        await room.local_participant.publish_track(track, options)

        # Wait for the browser participant's mic track to actually be subscribed
        # before greeting or listening — publishing audio/state any earlier risks
        # the browser missing it entirely, since LiveKit doesn't replay data
        # messages or audio frames sent before a participant finishes joining.
        greeted = False
        # Tracks the in-flight response task so a new utterance can barge in on
        # (cancel) a response that's still being generated/spoken.
        current_response_task: asyncio.Task | None = None

        @room.on("participant_connected")
        def on_participant_connected(participant: rtc.RemoteParticipant):
            logger.info("[VOICE] Participant connected: %s", participant.identity)

        @room.on("track_subscribed")
        def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
            nonlocal greeted
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info("[VOICE] Audio track subscribed from %s", participant.identity)
                if call_direction == "outbound" and not greeted:
                    greeted = True
                    asyncio.create_task(greet_then_listen(track))
                else:
                    asyncio.create_task(_publish_state(room, "listening"))
                    asyncio.create_task(handle_audio_track(track))

        async def greet_then_listen(audio_track: rtc.RemoteAudioTrack):
            customer_context = LoanService.get_customer_with_loans(customer_id)
            greeting_lang = (customer_context or {}).get("customer", {}).get("language", "en")
            greeting_text = agent.start_outbound(session_id, outbound_reason, customer_context, greeting_lang)
            logger.info("[VOICE] Outbound %s call — LoanMate speaking first (lang=%s)", outbound_reason, greeting_lang)
            CallTranscriptStore.append(session_id, "assistant", greeting_text)
            await _publish_state(room, "speaking")
            await _synthesize_and_publish(greeting_text, greeting_lang, tts, source)
            await _publish_state(room, "listening")
            await handle_audio_track(audio_track)

        async def handle_audio_track(audio_track: rtc.RemoteAudioTrack):
            nonlocal current_response_task
            stream = rtc.AudioStream(audio_track)
            audio_buffer = bytearray()
            silence_chunks = 0
            speech_start_ts: float | None = None

            # Calibrate an ambient noise floor from the first _CALIBRATION_MS of
            # audio instead of trusting one fixed RMS threshold for every mic/
            # room — real microphone audio (echo cancellation, noise suppression,
            # AGC all applied by the browser) has a very different amplitude
            # profile per device than the clean synthetic audio this was
            # originally tuned against.
            noise_samples: list[int] = []
            calibrated_ms = 0.0
            threshold = float(_SILENCE_AMPLITUDE)
            calibrated = False

            frame_count = 0
            speech_frame_count = 0

            async for event in stream:
                pcm_chunk = event.frame.data
                rms = audioop.rms(pcm_chunk, 2)
                chunk_ms = (len(pcm_chunk) // 2) / 48  # sample rate 48000 -> 48 samples per ms
                frame_count += 1

                if not calibrated:
                    noise_samples.append(rms)
                    calibrated_ms += chunk_ms
                    if calibrated_ms >= _CALIBRATION_MS:
                        noise_floor = sum(noise_samples) / len(noise_samples)
                        threshold = max(_SILENCE_AMPLITUDE, noise_floor * _NOISE_FLOOR_MULTIPLIER)
                        calibrated = True
                        logger.info(
                            "[VAD] Calibrated from %d frames: noise_floor=%.1f -> speech_threshold=%.1f",
                            len(noise_samples), noise_floor, threshold,
                        )
                    continue  # don't treat the calibration window itself as speech

                if frame_count % 250 == 0:
                    logger.info(
                        "[VAD] frames=%d rms=%d threshold=%.1f buffered_ms=%.0f",
                        frame_count, rms, threshold, (len(audio_buffer) // 2) / 48,
                    )

                if rms > threshold:
                    if len(audio_buffer) == 0:
                        speech_start_ts = time.monotonic()
                        logger.info("[VOICE] Speech started (rms=%d > threshold=%.1f)", rms, threshold)

                        # Barge-in: the user started talking while a previous
                        # response is still being generated or spoken — cancel it
                        # so LoanMate stops and handles the new utterance instead
                        # of talking over the user or ignoring them.
                        if current_response_task is not None and not current_response_task.done():
                            logger.info("[VOICE] Barge-in detected — cancelling in-flight response")
                            current_response_task.cancel()
                    speech_frame_count += 1
                    audio_buffer.extend(pcm_chunk)
                    silence_chunks = 0
                else:
                    silence_chunks += 1
                    if len(audio_buffer) > 0:
                        audio_buffer.extend(pcm_chunk)

                silence_ms = silence_chunks * chunk_ms
                speech_ms = (len(audio_buffer) // 2) / 48

                if len(audio_buffer) > 0 and silence_ms >= _SILENCE_THRESHOLD_MS and speech_ms >= _MIN_SPEECH_MS:
                    utterance = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    silence_chunks = 0
                    speech_end_ts = time.monotonic()
                    logger.info(
                        "[VOICE] Speech ended: utterance=%.0fms silence=%.0fms speech_frames=%d",
                        speech_ms, silence_ms, speech_frame_count,
                    )
                    speech_frame_count = 0

                    current_response_task = asyncio.create_task(
                        process_utterance(
                            audio_buffer=utterance,
                            customer_id=customer_id,
                            session_id=session_id,
                            source=source,
                            stt=stt,
                            agent=agent,
                            tts=tts,
                            room=room,
                            speech_end_ts=speech_end_ts,
                            call_direction=call_direction,
                            outbound_reason=outbound_reason,
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
