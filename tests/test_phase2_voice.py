"""
Phase 2 integration tests for the Voice Pipeline.
"""

from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app
import base64

client = TestClient(app)


@patch("backend.services.voice_service.TTSService.synthesize", new_callable=AsyncMock)
@patch("backend.services.voice_service.STTService.transcribe", new_callable=AsyncMock)
def test_voice_pipeline_english(mock_stt, mock_tts):
    """Test the full STT -> LLM -> TTS pipeline for an English query."""
    
    # Mock STT to return a specific phrase
    mock_stt.return_value = "What is my EMI?"
    
    # Mock TTS to return dummy audio bytes
    dummy_audio = b"dummy_audio_bytes"
    mock_tts.return_value = dummy_audio
    
    # Create a dummy WAV file for upload
    dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    
    response = client.post(
        "/api/voice/query/audio",
        data={"customer_id": "CUST001", "language": "en", "session_id": "test_voice_1"},
        files={"audio": ("test.wav", dummy_wav, "audio/wav")}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Check that STT was called
    mock_stt.assert_called_once()
    
    # Check that TTS was called
    mock_tts.assert_called_once()
    
    # Check response structure
    assert data["transcribed_text"] == "What is my EMI?"
    assert data["intent"] == "emi_query"
    assert data["audio_base64"] == base64.b64encode(dummy_audio).decode("utf-8")


@patch("backend.services.voice_service.TTSService.synthesize", new_callable=AsyncMock)
@patch("backend.services.voice_service.STTService.transcribe", new_callable=AsyncMock)
def test_voice_pipeline_hindi(mock_stt, mock_tts):
    """Test the full STT -> LLM -> TTS pipeline for a Hindi query."""
    
    # Mock STT to return a specific Hindi phrase
    mock_stt.return_value = "Meri EMI kitni hai?"
    mock_tts.return_value = b"hindi_audio"
    
    dummy_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    
    response = client.post(
        "/api/voice/query/audio",
        data={"customer_id": "CUST001", "language": "hi", "session_id": "test_voice_2"},
        files={"audio": ("test.wav", dummy_wav, "audio/wav")}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["transcribed_text"] == "Meri EMI kitni hai?"
    assert data["intent"] == "emi_query"
    assert data["audio_base64"] == base64.b64encode(b"hindi_audio").decode("utf-8")


@patch("backend.services.voice_service.TTSService.synthesize", new_callable=AsyncMock)
@patch("backend.services.voice_service.STTService.transcribe", new_callable=AsyncMock)
def test_voice_pipeline_empty_audio_error_handling(mock_stt, mock_tts):
    """Test error handling when STT fails or audio is unclear."""
    
    # Mock STT to return empty string (e.g. silent audio or error)
    mock_stt.return_value = ""
    mock_tts.return_value = b"error_audio"
    
    dummy_wav = b"empty_audio"
    
    response = client.post(
        "/api/voice/query/audio",
        data={"customer_id": "CUST001", "language": "en", "session_id": "test_voice_3"},
        files={"audio": ("test.wav", dummy_wav, "audio/wav")}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Expecting the graceful fallback text from VoiceService
    assert "clearly" in data["reply_text"].lower()
    assert data["intent"] == "other"
    assert data["transcribed_text"] == ""
    assert data["audio_base64"] == base64.b64encode(b"error_audio").decode("utf-8")

