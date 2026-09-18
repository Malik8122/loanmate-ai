"""
ISOLATED PROTOTYPE — Google Cloud Text-to-Speech Indian-voice evaluation.

This file is NOT wired into the production realtime path
(backend/voice_agent/realtime_agent.py is untouched and still the only
thing FastAPI/React actually talk to). It exists purely to let us
measure whether Google Cloud TTS's Indian voices (e.g. en-IN / hi-IN
Chirp 3 HD) sound meaningfully more Indian than Gemini Live's native
voices, and at what latency/barge-in cost, BEFORE deciding whether a
hybrid architecture is worth building.

Requires Google Cloud Application Default Credentials (a service account
key, `gcloud auth application-default login`, or equivalent) — NOT the
Gemini API key already used elsewhere in this project. Those are two
separate Google credential systems. If ADC is not configured, this
script reports that plainly and exits without touching anything else in
the app.

Run standalone:
    python -m backend.voice_agent.prototype_cloud_tts
"""

from __future__ import annotations

import os
import sys
import time
import wave

try:
    from google.cloud import texttospeech
    HAS_CLOUD_TTS_SDK = True
except ImportError:
    HAS_CLOUD_TTS_SDK = False

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "_cloud_tts_prototype_samples")

# NOTE: these voice name strings follow Google's publicly documented
# naming convention for Chirp 3 HD voices (e.g. "<locale>-Chirp3-HD-<name>"),
# but have NOT been verified against a live list_voices() call, because
# that call itself requires the credentials this script found missing.
# Do not treat these as confirmed-available without running
# list_voices() successfully first.
CANDIDATE_INDIAN_VOICES = [
    ("en-IN", "en-IN-Chirp3-HD-Achernar"),
    ("hi-IN", "hi-IN-Chirp3-HD-Achernar"),
]

TEST_SENTENCES = [
    ("english_greeting", "en-IN", "Hi Rajesh, this is LoanMate calling from your bank. Is this a good time for a quick update?"),
    ("hindi_greeting", "hi-IN", "Namaste Rajesh, main LoanMate bol raha hoon. Aapke loan ke baare mein ek quick update tha."),
    ("english_emi", "en-IN", "Your monthly EMI is thirty-one thousand five hundred rupees."),
    ("hindi_emi", "hi-IN", "Mera EMI ikattis hazaar paanch sau rupaye hai."),
]


def check_credentials() -> tuple[bool, str]:
    """Empirically test ADC by trying a real, cheap API call
    (list_voices) rather than just checking env vars — an env var could
    point at an invalid/expired file.
    """
    if not HAS_CLOUD_TTS_SDK:
        return False, "google-cloud-texttospeech is not installed"
    try:
        client = texttospeech.TextToSpeechClient()
        client.list_voices(language_code="en-IN")
        return True, "ADC credentials are valid and usable"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def run_prototype() -> None:
    ok, detail = check_credentials()
    if not ok:
        print("Google Cloud TTS prototype blocked because GCP credentials are not configured.")
        print(f"Detail: {detail}")
        print(
            "This does NOT affect the production realtime path — "
            "backend/voice_agent/realtime_agent.py is untouched and still runs on "
            "Gemini Live only."
        )
        return

    print(f"Credentials OK: {detail}")
    os.makedirs(OUT_DIR, exist_ok=True)
    client = texttospeech.TextToSpeechClient()

    # Confirm which Indian Chirp 3 HD voices actually exist right now,
    # rather than trusting the hardcoded candidate list above.
    for locale in ("en-IN", "hi-IN"):
        resp = client.list_voices(language_code=locale)
        chirp_voices = [v.name for v in resp.voices if "Chirp3" in v.name or "Chirp 3" in v.name]
        print(f"{locale} Chirp 3 HD voices actually available: {chirp_voices}")

    results = []
    for sid, locale, text in TEST_SENTENCES:
        voice_name = next((name for loc, name in CANDIDATE_INDIAN_VOICES if loc == locale), None)
        if not voice_name:
            continue
        t0 = time.monotonic()
        try:
            resp = client.synthesize_speech(
                input=texttospeech.SynthesisInput(text=text),
                voice=texttospeech.VoiceSelectionParams(language_code=locale, name=voice_name),
                audio_config=texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.LINEAR16, sample_rate_hertz=24000
                ),
            )
            t_ms = (time.monotonic() - t0) * 1000
            wav_path = os.path.join(OUT_DIR, f"{sid}.wav")
            with open(wav_path, "wb") as f:
                f.write(resp.audio_content)
            print(f"[{sid}] OK first-audio-available in {t_ms:.0f}ms -> {wav_path}")
            results.append({"sentence_id": sid, "ok": True, "latency_ms": t_ms, "wav_path": wav_path})
        except Exception as e:
            print(f"[{sid}] FAILED: {type(e).__name__}: {e}")
            results.append({"sentence_id": sid, "ok": False, "error": str(e)})

    print(f"\n{sum(1 for r in results if r['ok'])}/{len(results)} samples generated in {OUT_DIR}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    run_prototype()
