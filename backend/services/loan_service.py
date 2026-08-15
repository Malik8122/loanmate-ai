"""
Loan service business logic.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_MOCK_DATA_FILE = _DATA_DIR / "mock_data.json"
_KNOWLEDGE_FILE = _DATA_DIR / "loan_knowledge.json"


class LoanService:
    @staticmethod
    def _load_mock_data() -> dict:
        with open(_MOCK_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _save_mock_data(data: dict) -> None:
        with open(_MOCK_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @staticmethod
    def get_customer_with_loans(customer_id: str) -> dict[str, Any] | None:
        """Fetch customer details and their active loans."""
        data = LoanService._load_mock_data()
        
        customer = next((c for c in data.get("customers", []) if c["customer_id"] == customer_id), None)
        if not customer:
            return None

        loans = [L for L in data.get("loans", []) if L["customer_id"] == customer_id]
        
        return {
            "customer": customer,
            "loans": loans
        }

    @staticmethod
    def create_loan_application(customer_id: str, details: dict) -> str:
        """Create a mock loan application and return a reference ID."""
        data = LoanService._load_mock_data()
        
        app_id = f"APP{uuid.uuid4().hex[:6].upper()}"
        application = {
            "application_id": app_id,
            "customer_id": customer_id,
            "details": details,
            "status": "Pending",
            "timestamp": "2026-08-15T12:00:00Z" # Using static for prototype, can use datetime
        }
        
        data.setdefault("loan_applications", []).append(application)
        LoanService._save_mock_data(data)
        
        return app_id

    @staticmethod
    def get_loan_knowledge() -> dict:
        """Load the structured loan knowledge base."""
        if not _KNOWLEDGE_FILE.exists():
            return {}
        with open(_KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
