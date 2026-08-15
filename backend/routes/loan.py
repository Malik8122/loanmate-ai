"""
Loan & EMI information routes.
"""

from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "mock_data.json"


def _load_data() -> dict:
    """Load mock data from disk."""
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/emi/{customer_id}")
async def get_emi_details(customer_id: str):
    """Return EMI details for a given customer."""
    data = _load_data()
    for customer in data.get("customers", []):
        if customer["customer_id"] == customer_id:
            loans = [
                loan for loan in data.get("loans", [])
                if loan["customer_id"] == customer_id
            ]
            return {
                "customer_id": customer_id,
                "name": customer["name"],
                "loans": loans,
            }
    raise HTTPException(status_code=404, detail="Customer not found")


@router.get("/summary/{customer_id}")
async def get_loan_summary(customer_id: str):
    """Return an aggregated loan summary for a customer."""
    data = _load_data()
    loans = [
        loan for loan in data.get("loans", [])
        if loan["customer_id"] == customer_id
    ]
    if not loans:
        raise HTTPException(status_code=404, detail="No loans found for this customer")

    total_outstanding = sum(loan["outstanding_amount"] for loan in loans)
    total_emi = sum(loan["emi"] for loan in loans)

    return {
        "customer_id": customer_id,
        "total_loans": len(loans),
        "total_outstanding": total_outstanding,
        "total_monthly_emi": total_emi,
        "loans": loans,
    }
