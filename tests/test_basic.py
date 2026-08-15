"""
Basic smoke tests for the BFSI Voice Assistant backend.
"""

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_health_check():
    """GET /health should return 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_customer_list():
    """GET /api/customer/list should return a non-empty list."""
    response = client.get("/api/customer/list")
    assert response.status_code == 200
    customers = response.json()
    assert isinstance(customers, list)
    assert len(customers) > 0


def test_customer_detail():
    """GET /api/customer/CUST001 should return Rajesh Kumar."""
    response = client.get("/api/customer/CUST001")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Rajesh Kumar"


def test_customer_not_found():
    """GET /api/customer/INVALID should return 404."""
    response = client.get("/api/customer/INVALID")
    assert response.status_code == 404


def test_loan_emi():
    """GET /api/loan/emi/CUST001 should return loan data."""
    response = client.get("/api/loan/emi/CUST001")
    assert response.status_code == 200
    data = response.json()
    assert data["customer_id"] == "CUST001"
    assert len(data["loans"]) > 0


def test_loan_summary():
    """GET /api/loan/summary/CUST003 should return aggregated data."""
    response = client.get("/api/loan/summary/CUST003")
    assert response.status_code == 200
    data = response.json()
    assert data["total_loans"] == 2


def test_text_query():
    """POST /api/voice/query/text should return a placeholder reply."""
    response = client.post(
        "/api/voice/query/text",
        json={"customer_id": "CUST001", "text": "What is my EMI?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "reply_text" in data
