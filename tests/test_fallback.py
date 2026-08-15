"""
Fallback mode tests for the BFSI Voice Assistant.

These tests verify that when Gemini/API is unavailable the rule-based fallback:
  1. Returns personalized data read from mock customer/loan records.
  2. Never exposes [Fallback] markers or technical messages to the customer.
  3. Recognises queries in English, Hindi, and Hinglish.
  4. Handles unknown queries with a polite response.

Mock data reference (from backend/data/mock_data.json):
  CUST001 – Rajesh Kumar
    LN10001  Home Loan    EMI=31500  outstanding=2870000  due=2026-09-05  tenure=168  status=Active
    LN10002  Personal Loan EMI=14500  outstanding=320000   due=2026-09-05  tenure=24   status=Active
  CUST002 – Priya Sharma
    LN10003  Car Loan     EMI=17200  outstanding=580000   due=2026-09-10  tenure=36   status=Active
  CUST003 – Amit Patel
    LN10004  Home Loan    EMI=42000  outstanding=4100000  due=2026-09-01  tenure=216  status=Active
    LN10005  Education Loan EMI=18500 outstanding=950000  due=2026-09-15  tenure=60   status=Active
  CUST005 – Mohammed Irfan
    LN10007  Business Loan EMI=35000 outstanding=1750000  due=2026-09-05  tenure=54   status=Overdue
    LN10008  Gold Loan     EMI=9500  outstanding=0        due=null        tenure=0    status=Closed
"""

import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _post(customer_id: str, text: str, language: str = "en") -> dict:
    """Submit a text query and return the parsed JSON response."""
    resp = client.post(
        "/api/voice/query/text",
        json={
            "customer_id": customer_id,
            "text": text,
            "language": language,
            "session_id": "fallback_test",
        },
    )
    assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
    return resp.json()


def _no_fallback_marker(reply: str) -> None:
    """Assert the customer never sees a [Fallback] marker or technical message."""
    lower = reply.lower()
    assert "[fallback" not in lower, f"Fallback marker exposed: {reply!r}"
    assert "api key" not in lower, f"Technical message exposed: {reply!r}"
    assert "gemini" not in lower, f"Technical message exposed: {reply!r}"
    assert "api unavailable" not in lower, f"Technical message exposed: {reply!r}"


# ---------------------------------------------------------------------------
# 1. English EMI query → correct EMI from mock data (CUST002, Car Loan ₹17,200)
# ---------------------------------------------------------------------------

class TestEMIQuery:
    def test_english_what_is_my_emi(self):
        data = _post("CUST002", "What is my EMI?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_query"
        assert "17,200" in data["reply_text"] or "17200" in data["reply_text"]

    def test_english_how_much_is_my_emi(self):
        data = _post("CUST002", "How much is my EMI?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_query"
        assert "17,200" in data["reply_text"] or "17200" in data["reply_text"]

    def test_hindi_emi_kitni_hai(self):
        """Hindi: Meri EMI kitni hai?"""
        data = _post("CUST002", "Meri EMI kitni hai?", language="hi")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_query"
        assert "17,200" in data["reply_text"] or "17200" in data["reply_text"]

    def test_hinglish_mera_emi_kitna_hai(self):
        """Hinglish: Mera EMI kitna hai?"""
        data = _post("CUST002", "Mera EMI kitna hai?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_query"
        assert "17,200" in data["reply_text"] or "17200" in data["reply_text"]

    def test_hinglish_emi_kitni_hai(self):
        """Hinglish bare form: EMI kitni hai?"""
        data = _post("CUST002", "EMI kitni hai?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_query"
        assert "17,200" in data["reply_text"] or "17200" in data["reply_text"]

    def test_emi_correct_for_different_customer(self):
        """CUST003 first active loan is Home Loan with EMI 42,000."""
        data = _post("CUST003", "What is my EMI?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_query"
        assert "42,000" in data["reply_text"] or "42000" in data["reply_text"]


# ---------------------------------------------------------------------------
# 2. Outstanding balance query → correct amount from mock data
# ---------------------------------------------------------------------------

class TestOutstandingQuery:
    def test_english_outstanding(self):
        """CUST002 outstanding = ₹5,80,000."""
        data = _post("CUST002", "How much is my outstanding?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "outstanding_query"
        assert "5,80,000" in data["reply_text"] or "580000" in data["reply_text"] or "580,000" in data["reply_text"]

    def test_english_outstanding_balance(self):
        data = _post("CUST002", "What is my outstanding balance?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "outstanding_query"
        assert "5,80,000" in data["reply_text"] or "580000" in data["reply_text"] or "580,000" in data["reply_text"]

    def test_hinglish_outstanding_kitna_hai(self):
        """Hinglish: Outstanding kitna hai?"""
        data = _post("CUST002", "Outstanding kitna hai?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "outstanding_query"
        assert "5,80,000" in data["reply_text"] or "580000" in data["reply_text"] or "580,000" in data["reply_text"]

    def test_hindi_mera_outstanding_amount(self):
        """Hindi: Mera outstanding amount?"""
        data = _post("CUST002", "Mera outstanding amount?", language="hi")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "outstanding_query"

    def test_outstanding_correct_for_different_customer(self):
        """CUST001 first active loan outstanding = ₹28,70,000."""
        data = _post("CUST001", "How much is my outstanding?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "outstanding_query"
        assert "28,70,000" in data["reply_text"] or "2870000" in data["reply_text"] or "2,870,000" in data["reply_text"]


# ---------------------------------------------------------------------------
# 3. Due-date / Next EMI query
# ---------------------------------------------------------------------------

class TestDueDateQuery:
    def test_english_when_is_next_emi_due(self):
        """CUST002 Car Loan due date = 2026-09-10."""
        data = _post("CUST002", "When is my next EMI due?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_due_date"
        assert "2026-09-10" in data["reply_text"]

    def test_hindi_meri_next_emi_kab_hai(self):
        """Hindi: Meri next EMI kab hai?"""
        data = _post("CUST002", "Meri next EMI kab hai?", language="hi")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_due_date"
        assert "2026-09-10" in data["reply_text"]

    def test_hinglish_emi_kab_hai(self):
        """Hinglish: EMI kab hai?"""
        data = _post("CUST001", "EMI kab hai?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "emi_due_date"
        # CUST001 first active loan due = 2026-09-05
        assert "2026-09-05" in data["reply_text"]


# ---------------------------------------------------------------------------
# 4. Loan status query
# ---------------------------------------------------------------------------

class TestLoanStatusQuery:
    def test_english_loan_status(self):
        """CUST002 loan is Active."""
        data = _post("CUST002", "What is my loan status?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "loan_status"
        assert "active" in data["reply_text"].lower() or "Active" in data["reply_text"]

    def test_hindi_loan_status_kya_hai(self):
        """Hindi: Mera loan status kya hai?"""
        data = _post("CUST002", "Mera loan status kya hai?", language="hi")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "loan_status"

    def test_hinglish_status_kya(self):
        """Hinglish: Loan status kya?"""
        data = _post("CUST005", "Loan status kya?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "loan_status"
        # CUST005 first *active* loan (Business Loan) is Overdue
        assert "overdue" in data["reply_text"].lower() or "Overdue" in data["reply_text"]


# ---------------------------------------------------------------------------
# 5. Remaining EMI / tenure queries
# ---------------------------------------------------------------------------

class TestRemainingEMIQuery:
    def test_english_how_many_emis_remaining(self):
        """CUST002 Car Loan remaining tenure = 36."""
        data = _post("CUST002", "How many EMIs are remaining?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "remaining_emi"
        assert "36" in data["reply_text"]

    def test_hinglish_mere_kitne_emi_remaining(self):
        """Hinglish: Mere kitne EMI remaining hain?"""
        data = _post("CUST002", "Mere kitne EMI remaining hain?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "remaining_emi"
        assert "36" in data["reply_text"]


# ---------------------------------------------------------------------------
# 6. Unknown query → polite response, no error, no markers
# ---------------------------------------------------------------------------

class TestUnknownQuery:
    def test_unknown_query_polite_response(self):
        data = _post("CUST001", "What is the weather today?")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "other"
        assert data["escalate"] is False
        # Should contain a hint about what the assistant can help with
        assert len(data["reply_text"]) > 10

    def test_empty_ish_query(self):
        data = _post("CUST001", "Hmm...")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "other"


# ---------------------------------------------------------------------------
# 7. Escalation
# ---------------------------------------------------------------------------

class TestEscalation:
    def test_escalate_to_human_agent(self):
        data = _post("CUST001", "I want to talk to a human agent")
        _no_fallback_marker(data["reply_text"])
        assert data["intent"] == "escalate"
        assert data["escalate"] is True
