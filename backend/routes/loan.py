"""
Loan & EMI information routes.
"""

from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

from backend.services.loan_service import LoanService
from backend.tools import calculator_tools, loan_tools
from backend.models.schemas import (
    EmiCalculationRequest, EmiCalculationResponse,
    PrepaymentSimulationRequest, PrepaymentSimulationResponse,
    TenureComparisonRequest, TenureComparisonResponse,
    EligibilityRequest, EligibilityResponse,
)

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

@router.get("/knowledge")
async def get_loan_knowledge():
    """Return the structured loan knowledge base."""
    return LoanService.get_loan_knowledge()


@router.post("/calculate-emi", response_model=EmiCalculationResponse)
async def calculate_emi(request: EmiCalculationRequest):
    """Standalone EMI calculator — deterministic Python math, no LLM involved."""
    try:
        emi = calculator_tools.calculate_emi(request.principal, request.annual_rate, request.tenure_months)
        total_interest = calculator_tools.calculate_total_interest(request.principal, request.annual_rate, request.tenure_months)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return EmiCalculationResponse(
        emi=emi,
        total_interest=total_interest,
        total_payment=round(request.principal + total_interest, 2),
    )


@router.post("/simulate-prepayment", response_model=PrepaymentSimulationResponse)
async def simulate_prepayment(request: PrepaymentSimulationRequest):
    """Estimate the effect of a lump-sum prepayment on the customer's primary loan.

    This is a demo simulation, not an official bank quote — the frontend
    must label it as such.
    """
    customer_context = LoanService.get_customer_with_loans(request.customer_id)
    if not customer_context:
        raise HTTPException(status_code=404, detail=f"Customer {request.customer_id} not found.")

    loan = loan_tools.get_loan_details(customer_context)
    if not loan:
        raise HTTPException(status_code=404, detail="No loan found for this customer.")

    try:
        result = calculator_tools.calculate_prepayment(
            outstanding=loan["outstanding_amount"],
            annual_rate=loan["interest_rate"],
            remaining_months=loan["remaining_tenure"],
            prepayment_amount=request.prepayment_amount,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return PrepaymentSimulationResponse(
        loan_type=loan["loan_type"],
        current_outstanding=loan["outstanding_amount"],
        current_emi=result["current_emi"],
        prepayment_amount=request.prepayment_amount,
        new_outstanding=result["new_outstanding"],
        new_emi=result["new_emi"],
        emi_reduction=result["emi_reduction"],
        loan_closed=result["loan_closed"],
    )


@router.post("/compare-tenures", response_model=TenureComparisonResponse)
async def compare_tenures(request: TenureComparisonRequest):
    """Compare EMI/interest/total payment across candidate tenures for the
    customer's primary loan principal and rate.
    """
    customer_context = LoanService.get_customer_with_loans(request.customer_id)
    if not customer_context:
        raise HTTPException(status_code=404, detail=f"Customer {request.customer_id} not found.")

    loan = loan_tools.get_loan_details(customer_context)
    if not loan:
        raise HTTPException(status_code=404, detail="No loan found for this customer.")

    if len(request.tenure_years) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two tenure options to compare.")

    months = [y * 12 for y in request.tenure_years]
    try:
        comparison = calculator_tools.compare_tenures(loan["loan_amount"], loan["interest_rate"], months)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TenureComparisonResponse(loan_type=loan["loan_type"], comparison=comparison)


@router.post("/eligibility", response_model=EligibilityResponse)
async def check_eligibility(request: EligibilityRequest):
    """Demo eligibility estimate — NOT an actual lending decision."""
    try:
        result = calculator_tools.calculate_loan_eligibility(
            monthly_income=request.monthly_income,
            existing_emi=request.existing_emi,
            proposed_amount=request.proposed_amount,
            annual_rate=request.annual_rate,
            tenure_months=request.tenure_months,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return EligibilityResponse(**result)
