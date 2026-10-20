"""
Call records — what inbound and outbound calls left behind.

Inbound calls raise service requests (with reference numbers); outbound
campaign calls each record one outcome (promise to pay, callback, not
interested, ...). See backend/services/call_records.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from backend.services import call_records
from backend.voice_agent.call_context import VALID_OUTBOUND_REASONS

router = APIRouter()


@router.get("/records")
async def get_call_records(
    customer_id: str | None = Query(None, description="Only records for this customer"),
    kind: str | None = Query(None, pattern="^(service_request|call_outcome)$", description="Only this kind of record"),
    limit: int = Query(50, ge=1, le=500),
):
    """Most recent service requests and outbound call outcomes, newest first."""
    return {"records": call_records.list_records(customer_id=customer_id, kind=kind, limit=limit)}


@router.get("/purposes")
async def get_call_purposes():
    """What each call direction is for — handy for the UI and for documentation."""
    return {
        "inbound": {
            "purpose": "Customer-initiated service call: answer questions and raise service requests.",
            "service_request_types": call_records.SERVICE_REQUEST_TYPES,
        },
        "outbound": {
            "purpose": "Bank-initiated campaign call with one purpose; ends with a recorded outcome.",
            "reasons": {reason: sorted(call_records.OUTBOUND_OUTCOMES[reason]) for reason in sorted(VALID_OUTBOUND_REASONS)},
        },
    }
