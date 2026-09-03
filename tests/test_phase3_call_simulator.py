"""
Phase 3 tests: the standalone TTS endpoint and the richer conversational
fallback used by the Phone Call Simulator (bank name, assistant identity,
capabilities, and name introduction).
"""

from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.llm_service import LLMService

client = TestClient(app)


@patch("backend.services.voice_service.TTSService.synthesize", new_callable=AsyncMock)
def test_tts_endpoint_returns_audio(mock_tts):
    """POST /api/voice/tts should synthesize the given text without calling the LLM."""
    mock_tts.return_value = b"greeting_audio_bytes"

    response = client.post(
        "/api/voice/tts",
        json={"text": "Hello! Welcome to Unity Bank.", "language": "en"},
    )

    assert response.status_code == 200
    data = response.json()
    mock_tts.assert_called_once()
    assert data["audio_base64"] is not None


@patch("backend.services.voice_service.TTSService.synthesize", new_callable=AsyncMock)
def test_tts_endpoint_empty_text_returns_no_audio(mock_tts):
    """Empty text should not produce audio."""
    mock_tts.return_value = b""

    response = client.post("/api/voice/tts", json={"text": "", "language": "en"})

    assert response.status_code == 200
    assert response.json()["audio_base64"] is None


def _fallback_reply(message: str, language: str = "en") -> dict:
    service = LLMService()
    return service._fallback_response(message, language, customer_context=None)


def test_fallback_which_bank():
    result = _fallback_reply("Which bank is this?")
    assert "unity bank" in result["reply"].lower()


def test_fallback_assistant_identity():
    result = _fallback_reply("What is your name?")
    assert "assistant" in result["reply"].lower()


def test_fallback_capabilities():
    result = _fallback_reply("What can you help me with?")
    reply_lower = result["reply"].lower()
    assert "emi" in reply_lower
    assert "loan" in reply_lower


def test_fallback_name_introduction_english():
    result = _fallback_reply("My name is Arjun")
    assert "arjun" in result["reply"].lower()
    assert result["intent"] == "greeting"


def test_fallback_name_introduction_hindi():
    result = _fallback_reply("Mera naam Arjun hai", language="hi")
    assert "arjun" in result["reply"].lower()


def test_fallback_capability_question_does_not_escalate():
    """'What can you help me with' contains 'help me' but must not be
    misread as an escalation request."""
    result = _fallback_reply("What can you help me with?")
    assert result["escalate"] is False
