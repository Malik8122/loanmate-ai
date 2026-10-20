"""
Single source of truth for what a realtime voice call knows about who
it's talking to and why the call is happening.

Built server-side, once, from a customer_id that the route layer has
already validated against LoanService (see backend/routes/realtime.py).
Nothing here ever trusts a customer_name / loan_id / etc. supplied
directly by the browser — those are always re-derived from the resolved
customer record, never taken from client input.

Inbound and outbound calls have different purposes:

- inbound  — the customer called the bank. It is a SERVICE call: the
  customer leads, LoanMate answers questions and raises service requests.
- outbound — the bank called the customer for ONE specific campaign
  purpose (outbound_reason). LoanMate leads, confirms it is speaking to
  the right person, stays on that purpose, and records a call outcome.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CallMode = Literal["inbound", "outbound"]
OutboundReason = Literal["emi_reminder", "overdue_followup", "kyc_update", "product_update"]
Language = Literal["english", "hindi", "hinglish"]

VALID_OUTBOUND_REASONS: set[str] = {"emi_reminder", "overdue_followup", "kyc_update", "product_update"}
# Regex used by the route layer's Query(pattern=...) validation.
OUTBOUND_REASON_PATTERN = "^(" + "|".join(sorted(VALID_OUTBOUND_REASONS)) + "|auto)$"

# Gemini Live BCP-47 codes for the languages we explicitly support. Hinglish
# has no BCP-47 code of its own — pinning one (e.g. forcing en-IN or hi-IN)
# would fight the model's natural English/Hindi code-switching, so Hinglish
# deliberately maps to None (auto-detect) rather than to either single locale.
_GEMINI_LANGUAGE_CODES: dict[str, str] = {
    "english": "en-IN",
    "hindi": "hi-IN",
}


@dataclass(frozen=True)
class CallContext:
    customer_id: str
    customer_name: str
    loan_id: str | None
    loan_type: str | None
    call_mode: CallMode
    outbound_reason: OutboundReason | None
    language: Language

    @property
    def gemini_language_code(self) -> str | None:
        """BCP-47 code to pin the Gemini Live session to, or None to let it
        auto-detect / code-switch (used for Hinglish and as a safe default).
        """
        return _GEMINI_LANGUAGE_CODES.get(self.language)

    @property
    def first_name(self) -> str:
        """First name only, for a natural phone-call opener ("Hi Rajesh")
        — the full name stays available in the system context block for
        when the customer directly asks for it.
        """
        return self.customer_name.split()[0] if self.customer_name else self.customer_name


def _select_loan(loans: list[dict], reason: str | None) -> dict | None:
    """The loan a call is about: an overdue loan for an overdue follow-up,
    otherwise the first active loan, otherwise whatever is on file.
    """
    if reason == "overdue_followup":
        overdue = next((loan for loan in loans if loan.get("loan_status") == "Overdue"), None)
        if overdue:
            return overdue
    active = next((loan for loan in loans if loan.get("loan_status") == "Active"), None)
    return active or (loans[0] if loans else None)


def suggest_outbound_reason(customer_record: dict) -> OutboundReason:
    """Pick the campaign a bank would actually run for this customer, in
    priority order: an overdue loan beats a pending KYC, which beats a
    routine EMI reminder. Used when the caller asks for reason="auto" (or
    sends none).
    """
    customer = customer_record.get("customer") or {}
    loans = customer_record.get("loans") or []
    if any(loan.get("loan_status") == "Overdue" for loan in loans):
        return "overdue_followup"
    if customer and not customer.get("kyc_verified", True):
        return "kyc_update"
    if any(loan.get("loan_status") == "Active" for loan in loans):
        return "emi_reminder"
    return "product_update"


def resolve_outbound_reason(customer_record: dict, outbound_reason: str | None) -> OutboundReason:
    if outbound_reason in VALID_OUTBOUND_REASONS:
        return outbound_reason  # type: ignore[return-value]
    return suggest_outbound_reason(customer_record)


def build_call_context(
    customer_id: str,
    customer_record: dict,
    call_mode: str,
    outbound_reason: str | None,
    language: str,
) -> CallContext:
    """Build a CallContext from a customer record that the CALLER has
    already resolved and validated (LoanService.get_customer_with_loans).
    This function does no validation of its own — it only shapes trusted,
    server-resolved data into the concise structure the agent uses.
    """
    customer = customer_record.get("customer") or {}
    loans = customer_record.get("loans") or []

    resolved_mode: CallMode = "outbound" if call_mode == "outbound" else "inbound"

    resolved_reason: OutboundReason | None = None
    if resolved_mode == "outbound":
        resolved_reason = resolve_outbound_reason(customer_record, outbound_reason)

    loan = _select_loan(loans, resolved_reason)

    resolved_language: Language = language if language in ("english", "hindi", "hinglish") else "english"  # type: ignore[assignment]

    return CallContext(
        customer_id=customer_id,
        customer_name=customer.get("name") or "the customer",
        loan_id=loan.get("loan_id") if loan else None,
        loan_type=loan.get("loan_type") if loan else None,
        call_mode=resolved_mode,
        outbound_reason=resolved_reason,
        language=resolved_language,
    )
