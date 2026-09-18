"""
Read-only lookups over a customer's own loan data.

Every function takes the customer_context dict that the route layer
already scoped to a single customer_id (see LoanService.get_customer_with_loans)
— there is no customer_id parameter here, so a tool can't accidentally
be pointed at a different customer's records than the one the caller
already resolved and authorized.
"""

from __future__ import annotations

from typing import Any


def _primary_loan(customer_context: dict | None) -> dict | None:
    if not customer_context:
        return None
    loans = customer_context.get("loans", [])
    active = [loan for loan in loans if loan.get("loan_status") == "Active"]
    if active:
        return active[0]
    return loans[0] if loans else None


def get_customer_profile(customer_context: dict | None) -> dict | None:
    if not customer_context:
        return None
    return customer_context.get("customer")


def get_loan_details(customer_context: dict | None) -> dict | None:
    return _primary_loan(customer_context)


def get_emi(customer_context: dict | None) -> float | None:
    loan = _primary_loan(customer_context)
    return loan.get("emi") if loan else None


def get_outstanding_balance(customer_context: dict | None) -> float | None:
    loan = _primary_loan(customer_context)
    return loan.get("outstanding_amount") if loan else None


def get_next_payment(customer_context: dict | None) -> str | None:
    loan = _primary_loan(customer_context)
    return loan.get("due_date") if loan else None


def get_interest_rate(customer_context: dict | None) -> float | None:
    loan = _primary_loan(customer_context)
    return loan.get("interest_rate") if loan else None


def get_remaining_tenure(customer_context: dict | None) -> int | None:
    loan = _primary_loan(customer_context)
    return loan.get("remaining_tenure") if loan else None


def get_loan_status(customer_context: dict | None) -> str | None:
    loan = _primary_loan(customer_context)
    return loan.get("loan_status") if loan else None


def get_all_loans(customer_context: dict | None) -> list[dict[str, Any]]:
    if not customer_context:
        return []
    return customer_context.get("loans", [])


def get_payment_history(customer_context: dict | None) -> dict:
    """The mock dataset has no transaction-level payment history — only
    each loan's current due date/EMI/status. Say so honestly instead of
    fabricating past payments (see Phase 46 / no-fake-data rule).
    """
    loans = get_all_loans(customer_context)
    return {
        "has_transaction_history": False,
        "note": "Detailed past-payment history isn't available in this demo dataset.",
        "current_schedule": [
            {
                "loan_type": loan["loan_type"],
                "emi": loan["emi"],
                "next_due_date": loan.get("due_date"),
                "status": loan["loan_status"],
            }
            for loan in loans
        ],
    }
