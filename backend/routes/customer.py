"""
Customer information routes.
"""

from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter()

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "mock_data.json"


def _load_data() -> dict:
    with open(_DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/list")
async def list_customers():
    """Return a list of all mock customers (id + name)."""
    data = _load_data()
    return [
        {"customer_id": c["customer_id"], "name": c["name"], "phone": c["phone"]}
        for c in data.get("customers", [])
    ]


@router.get("/{customer_id}")
async def get_customer(customer_id: str):
    """Return full profile for a single customer."""
    data = _load_data()
    for customer in data.get("customers", []):
        if customer["customer_id"] == customer_id:
            return customer
    raise HTTPException(status_code=404, detail="Customer not found")
