"""
Pydantic schemas for request / response validation.
"""

from __future__ import annotations
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------

class CustomerBase(BaseModel):
    customer_id: str
    name: str
    phone: str
    email: str | None = None
    language: str = "en"
    city: str | None = None
    kyc_verified: bool = False


class CustomerListItem(BaseModel):
    customer_id: str
    name: str
    phone: str


# ---------------------------------------------------------------------------
# Loan
# ---------------------------------------------------------------------------

class LoanRecord(BaseModel):
    loan_id: str
    customer_id: str
    loan_type: str
    loan_amount: float
    interest_rate: float
    emi: float
    outstanding_amount: float
    due_date: str | None = None
    remaining_tenure: int = Field(..., description="Remaining months")
    loan_status: str
    disbursement_date: str | None = None


class LoanSummary(BaseModel):
    customer_id: str
    total_loans: int
    total_outstanding: float
    total_monthly_emi: float
    loans: list[LoanRecord]


# ---------------------------------------------------------------------------
# Loan Application
# ---------------------------------------------------------------------------

class LoanApplicationRequest(BaseModel):
    customer_id: str
    loan_type: str | None = None
    amount: float | None = None
    employment: str | None = None
    
class LoanApplicationResponse(BaseModel):
    application_id: str
    message: str


# ---------------------------------------------------------------------------
# Voice / Conversation
# ---------------------------------------------------------------------------

class TextQueryRequest(BaseModel):
    customer_id: str
    text: str
    language: str = "en"
    session_id: str = "default"


class AssistantResponse(BaseModel):
    reply_text: str
    audio_base64: str | None = None
    language: str = "en"
    intent: str = "other"
    escalate: bool = False
    session_id: str = "default"
    transcribed_text: str | None = None
