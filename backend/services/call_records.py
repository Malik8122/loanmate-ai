"""
What each kind of call leaves behind.

- An INBOUND call (the customer called the bank) can raise service
  requests — a statement, a no-dues certificate, a complaint, a human
  callback — each with a reference number the customer is given.
- An OUTBOUND call (the bank called the customer) ends with exactly one
  call outcome for its campaign — promise to pay, callback requested,
  not interested, wrong person, and so on.

Records are appended to a JSON-lines file rather than kept in memory
because the realtime agent (backend/voice_agent/realtime_agent.py) runs
as a separate worker process from the FastAPI app that serves
GET /api/calls/records — a file is the simplest thing both can see.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RECORDS_PATH = Path(__file__).resolve().parent.parent / "data" / "call_records.jsonl"

SERVICE_REQUEST_TYPES: dict[str, str] = {
    "account_statement": "Loan account statement",
    "no_dues_certificate": "No-dues / NOC certificate",
    "foreclosure_quote": "Foreclosure (full payoff) quote",
    "interest_certificate": "Interest certificate for tax",
    "document_return": "Return of original property documents",
    "update_contact_details": "Update contact details",
    "emi_date_change": "EMI date change",
    "restructuring_request": "Repayment difficulty / restructuring",
    "complaint": "Complaint",
    "fraud_report": "Suspected fraud report",
    "human_callback": "Callback from a human officer",
}

# Outcomes valid for each outbound campaign — the agent may only record an
# outcome that makes sense for the reason it called.
_COMMON_OUTCOMES = {"callback_requested", "not_interested", "do_not_call", "wrong_person", "no_response"}
OUTBOUND_OUTCOMES: dict[str, set[str]] = {
    "emi_reminder": _COMMON_OUTCOMES | {"will_pay_on_time", "promise_to_pay", "already_paid", "payment_difficulty"},
    "overdue_followup": _COMMON_OUTCOMES | {"promise_to_pay", "already_paid", "payment_difficulty", "dispute"},
    "kyc_update": _COMMON_OUTCOMES | {"will_update_kyc", "already_updated"},
    "product_update": _COMMON_OUTCOMES | {"interested", "needs_more_info"},
}

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(record: dict[str, Any]) -> None:
    with _lock:
        RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RECORDS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def raise_service_request(
    customer_id: str,
    request_type: str,
    details: str = "",
    session_id: str | None = None,
) -> dict[str, Any]:
    """Log an inbound service request and return it with its reference number."""
    if request_type not in SERVICE_REQUEST_TYPES:
        request_type = "human_callback"
    record = {
        "kind": "service_request",
        "reference": f"SR{secrets.randbelow(900000) + 100000}",
        "customer_id": customer_id,
        "session_id": session_id,
        "call_mode": "inbound",
        "request_type": request_type,
        "label": SERVICE_REQUEST_TYPES[request_type],
        "details": details.strip(),
        "status": "Open",
        "created_at": _now(),
    }
    _append(record)
    logger.info("[CALL RECORD] service_request %s %s for %s", record["reference"], request_type, customer_id)
    return record


def record_call_outcome(
    customer_id: str,
    outbound_reason: str,
    outcome: str,
    promised_date: str | None = None,
    promised_amount: float | None = None,
    callback_time: str | None = None,
    notes: str = "",
    session_id: str | None = None,
) -> dict[str, Any]:
    """Log the outcome of an outbound campaign call.

    Raises ValueError for an outcome that doesn't belong to the campaign,
    so the agent gets told and can pick a valid one.
    """
    allowed = OUTBOUND_OUTCOMES.get(outbound_reason, _COMMON_OUTCOMES)
    if outcome not in allowed:
        raise ValueError(f"'{outcome}' is not a valid outcome for a {outbound_reason} call. Valid: {sorted(allowed)}")
    record = {
        "kind": "call_outcome",
        "customer_id": customer_id,
        "session_id": session_id,
        "call_mode": "outbound",
        "outbound_reason": outbound_reason,
        "outcome": outcome,
        "promised_date": promised_date,
        "promised_amount": promised_amount,
        "callback_time": callback_time,
        "notes": notes.strip(),
        "created_at": _now(),
    }
    _append(record)
    logger.info("[CALL RECORD] outcome %s (%s) for %s", outcome, outbound_reason, customer_id)
    return record


def list_records(customer_id: str | None = None, kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Most recent records first, optionally filtered by customer and kind."""
    if not RECORDS_PATH.exists():
        return []
    with _lock:
        lines = RECORDS_PATH.read_text(encoding="utf-8").splitlines()
    records = []
    for line in reversed(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if customer_id and record.get("customer_id") != customer_id:
            continue
        if kind and record.get("kind") != kind:
            continue
        records.append(record)
        if len(records) >= limit:
            break
    return records
