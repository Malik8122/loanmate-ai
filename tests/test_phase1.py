"""
Phase 1 integration tests.
"""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_loan_knowledge():
    """GET /api/loan/knowledge returns the KB."""
    response = client.get("/api/loan/knowledge")
    assert response.status_code == 200
    data = response.json()
    assert "loan_products" in data


def test_voice_text_query_fallback():
    """Test text query fallback returns a real EMI value from mock data (no API key needed)."""
    # CUST001 has EMI 31,500 (Home Loan, first active loan)
    response = client.post(
        "/api/voice/query/text",
        json={"customer_id": "CUST001", "text": "What is my EMI?", "language": "en", "session_id": "test_session_1"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply_text" in data
    # Should NOT expose internal [Fallback] markers to the customer
    assert "[Fallback" not in data["reply_text"]
    assert "[fallback" not in data["reply_text"].lower()
    # Should contain the real EMI value from mock data
    assert "31,500" in data["reply_text"] or "31500" in data["reply_text"]
    # Intent should be recognised
    assert data["intent"] == "emi_query"


def test_voice_text_query_escalate_fallback():
    """Test escalate intent in fallback."""
    response = client.post(
        "/api/voice/query/text",
        json={"customer_id": "CUST001", "text": "I want to talk to an agent", "language": "en", "session_id": "test_session_2"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "escalate"
    assert data["escalate"] is True


def test_loan_application_submit():
    """Test submitting a loan application."""
    response = client.post(
        "/api/apply/submit",
        json={"customer_id": "CUST002", "loan_type": "Personal Loan", "amount": 500000.0, "employment": "Salaried"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "application_id" in data
    assert "APP" in data["application_id"]
    assert "submitted successfully" in data["message"]
