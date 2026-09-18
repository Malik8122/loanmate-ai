"""
Single source of truth for what a realtime voice call knows about who
it's talking to and why the call is happening.

Built server-side, once, from a customer_id that the route layer has
already validated against LoanService (see backend/routes/realtime.py).
Nothing here ever trusts a customer_name / loan_id / etc. supplied
directly by the browser — those are always re-derived from the resolved
customer record, never taken from client input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CallMode = Literal["inbound", "outbound"]
OutboundReason = Literal["product_update", "emi_reminder"]
Language = Literal["english", "hindi", "hinglish"]

VALID_OUTBOUND_REASONS: set[str] = {"product_update", "emi_reminder"}
_DEFAULT_OUTBOUND_REASON: OutboundReason = "product_update"

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
    active_loan = next((loan for loan in loans if loan.get("loan_status") == "Active"), None)
    active_loan = active_loan or (loans[0] if loans else None)

    resolved_mode: CallMode = "outbound" if call_mode == "outbound" else "inbound"

    resolved_reason: OutboundReason | None = None
    if resolved_mode == "outbound":
        resolved_reason = (
            outbound_reason if outbound_reason in VALID_OUTBOUND_REASONS else _DEFAULT_OUTBOUND_REASON
        )  # type: ignore[assignment]

    resolved_language: Language = language if language in ("english", "hindi", "hinglish") else "english"  # type: ignore[assignment]

    return CallContext(
        customer_id=customer_id,
        customer_name=customer.get("name") or "the customer",
        loan_id=active_loan.get("loan_id") if active_loan else None,
        call_mode=resolved_mode,
        outbound_reason=resolved_reason,
        language=resolved_language,
    )
