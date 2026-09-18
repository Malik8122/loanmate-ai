"""
Small regex-based helpers for pulling numbers out of a user's message
(amounts in Indian lakh/crore phrasing, tenures in years). Used by the
orchestrator to fill in calculator tool arguments — if nothing usable
is found, the caller should ask the user to clarify rather than guess.
"""

from __future__ import annotations

import re


def parse_amount(text: str) -> float | None:
    """Parse a rupee amount, understanding "lakh"/"crore" phrasing."""
    text_lower = text.lower()

    m = re.search(r"([\d.]+)\s*(lakh|lac)", text_lower)
    if m:
        return float(m.group(1)) * 100_000

    m = re.search(r"([\d.]+)\s*crore", text_lower)
    if m:
        return float(m.group(1)) * 10_000_000

    m = re.search(r"₹?\s*([\d,]{4,})", text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            return None

    return None


def parse_tenure_years(text: str) -> list[int]:
    """Return every "<N> year(s)/yrs/saal" mention in the text, in order."""
    return [int(y) for y in re.findall(r"(\d+)\s*(?:years?|yrs?|saal)", text.lower())]
