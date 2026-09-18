"""
Deterministic financial calculators.

The LLM never does loan arithmetic itself — it only narrates numbers
these functions computed. That keeps every ₹ figure the assistant
says traceable to a plain Python formula instead of model guesswork.

All amounts are in rupees, tenures in months, rates as annual
percentages (e.g. 8.5 for 8.5%).
"""

from __future__ import annotations


def calculate_emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Standard reducing-balance EMI formula."""
    if principal <= 0 or tenure_months <= 0:
        raise ValueError("principal and tenure_months must be positive")
    if annual_rate <= 0:
        return round(principal / tenure_months, 2)

    monthly_rate = annual_rate / 12 / 100
    factor = (1 + monthly_rate) ** tenure_months
    emi = principal * monthly_rate * factor / (factor - 1)
    return round(emi, 2)


def calculate_total_interest(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Total interest paid over the full tenure at a given EMI."""
    emi = calculate_emi(principal, annual_rate, tenure_months)
    return round(emi * tenure_months - principal, 2)


def calculate_prepayment(
    outstanding: float,
    annual_rate: float,
    remaining_months: int,
    prepayment_amount: float,
) -> dict:
    """Effect of a lump-sum prepayment, keeping the remaining tenure fixed
    and reducing the EMI instead (the common "reduce EMI" prepayment option).
    """
    if prepayment_amount <= 0:
        raise ValueError("prepayment_amount must be positive")
    if prepayment_amount >= outstanding:
        return {
            "new_outstanding": 0.0,
            "current_emi": calculate_emi(outstanding, annual_rate, remaining_months),
            "new_emi": 0.0,
            "emi_reduction": calculate_emi(outstanding, annual_rate, remaining_months),
            "loan_closed": True,
        }

    current_emi = calculate_emi(outstanding, annual_rate, remaining_months)
    new_outstanding = round(outstanding - prepayment_amount, 2)
    new_emi = calculate_emi(new_outstanding, annual_rate, remaining_months)

    return {
        "new_outstanding": new_outstanding,
        "current_emi": current_emi,
        "new_emi": new_emi,
        "emi_reduction": round(current_emi - new_emi, 2),
        "loan_closed": False,
    }


def calculate_loan_eligibility(
    monthly_income: float,
    existing_emi: float,
    proposed_amount: float,
    annual_rate: float,
    tenure_months: int,
    foir_limit: float = 0.5,
) -> dict:
    """A simplified FOIR (Fixed Obligation to Income Ratio) demo estimate.

    This is NOT a real underwriting decision — it's a rough, transparent
    affordability check for demo purposes only.
    """
    if monthly_income <= 0:
        raise ValueError("monthly_income must be positive")

    proposed_emi = calculate_emi(proposed_amount, annual_rate, tenure_months)
    total_obligation = existing_emi + proposed_emi
    foir = round(total_obligation / monthly_income, 3)

    if foir <= foir_limit:
        status = "eligible"
    elif foir <= foir_limit + 0.1:
        status = "possibly_eligible"
    else:
        status = "not_eligible"

    return {
        "proposed_emi": proposed_emi,
        "foir": foir,
        "foir_limit": foir_limit,
        "status": status,
    }


def compare_tenures(principal: float, annual_rate: float, tenure_options_months: list[int]) -> list[dict]:
    """EMI / total-interest / total-payment for each candidate tenure."""
    results = []
    for months in tenure_options_months:
        emi = calculate_emi(principal, annual_rate, months)
        total_interest = calculate_total_interest(principal, annual_rate, months)
        results.append({
            "tenure_months": months,
            "emi": emi,
            "total_interest": total_interest,
            "total_payment": round(principal + total_interest, 2),
        })
    return results
