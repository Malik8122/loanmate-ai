"""
Keyword-based intent classification, shared by the rule-based LLM
fallback and the agent orchestrator's tool router.

This is intentionally simple (substring keyword matching, not a
trained classifier) — it's transparent, has zero latency/cost, and
covers the demo's known question shapes in English, Hindi and
Hinglish. Order matters: more specific intents are checked first so
e.g. "next EMI due date" doesn't get caught by the generic EMI check.
"""

from __future__ import annotations

from backend.agents.glossary import find_glossary_term

# ── "Explain this term" trigger phrases — only glossary intent when paired
# with an actual glossary term AND no possessive ("my EMI" stays a real
# account question, not a request to define EMI in general).
_GLOSSARY_TRIGGERS = [
    "explain", "what is", "what's", "kya hota hai", "kya hai",
    "samjhao", "samjha do", "matlab", "define", "meaning of",
]
_POSSESSIVE_MARKERS = ["my ", "mera ", "meri ", "mere ", "apna ", "apni "]

# ── Prepayment / revised-EMI simulation ──────────────────────────────
_PREPAYMENT_KEYWORDS = [
    "prepay", "prepayment", "part payment", "partial payment",
    "foreclose", "foreclosure", "kam hogi", "kam ho jayegi",
    "revised emi", "agar main", "agar mai",
]
# ── Tenure / scenario comparison ─────────────────────────────────────
_COMPARISON_KEYWORDS = [
    "compare", "vs", "versus", "which is better", "tenure options",
]
# ── Eligibility ───────────────────────────────────────────────────────
_ELIGIBILITY_KEYWORDS = [
    "eligible", "eligibility", "qualify", "how much loan can i get",
    "kitna loan mil sakta",
]
# ── Due-date / Next EMI ───────────────────────────────────────────────
_DUE_KEYWORDS = [
    "next emi", "emi kab", "due date", "due kab", "kab hai",
    "kab bhari", "kab pay", "when is my emi", "when is the emi",
    "emi due", "kitne din", "due on", "next payment",
]
# ── Remaining EMIs / tenure ────────────────────────────────────────────
_REMAINING_KEYWORDS = [
    "remaining emi", "remaining tenure", "kitne emi", "kitni emi baki",
    "kitne emi baki", "emi baki", "bachi hai", "bache hain",
    "how many emi", "how many emis", "emi remaining", "tenure left",
    "mere kitne emi",
]
# ── Loan status ────────────────────────────────────────────────────────
_STATUS_KEYWORDS = [
    "loan status", "status kya", "loan kya hai", "mera loan",
    "loan active", "what is my loan", "loan ki sthiti",
]
# ── Outstanding ────────────────────────────────────────────────────────
_OUTSTANDING_KEYWORDS = [
    "outstanding", "baki kitna", "baki amount", "due amount",
    "baqi", "pending amount", "total due", "kitna baki",
    "how much is my outstanding", "outstanding amount",
    "loan balance", "remaining balance",
]
# ── EMI amount ─────────────────────────────────────────────────────────
_EMI_KEYWORDS = [
    "emi", "monthly payment", "monthly installment",
    "installment kitni", "emi kitni", "meri emi", "mera emi",
]
# ── Payment history ──────────────────────────────────────────────────
_PAYMENT_HISTORY_KEYWORDS = [
    "did i pay", "last payment", "payment history", "paid last month",
    "pichla payment", "maine pay kiya",
]
# ── Escalation ─────────────────────────────────────────────────────────
# Deliberately specific multi-word phrases only — bare words like "agent" or
# "help me" false-positive on innocuous questions like "how can you help me?"
# or "what does a loan agent do?".
_ESCALATE_KEYWORDS = [
    "human agent", "talk to a human", "speak to a human", "speak with a human",
    "connect me to a human", "connect me to an agent", "talk to an agent",
    "speak to an agent", "real person", "loan officer", "customer care",
    "human se baat", "insaan se baat", "agent se connect", "agent se baat",
    "manager se baat",
]
# ── Loan application ───────────────────────────────────────────────────
_APPLY_KEYWORDS = [
    "apply", "chahiye", "loan lena", "loan chahiye",
    "new loan", "naya loan",
]

INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("prepayment_simulation", _PREPAYMENT_KEYWORDS),
    ("comparison", _COMPARISON_KEYWORDS),
    ("eligibility", _ELIGIBILITY_KEYWORDS),
    ("emi_due_date", _DUE_KEYWORDS),
    ("remaining_emi", _REMAINING_KEYWORDS),
    ("loan_status", _STATUS_KEYWORDS),
    ("outstanding_query", _OUTSTANDING_KEYWORDS),
    ("payment_history", _PAYMENT_HISTORY_KEYWORDS),
    ("emi_query", _EMI_KEYWORDS),
    ("escalate", _ESCALATE_KEYWORDS),
    ("apply_loan", _APPLY_KEYWORDS),
]


def classify_intent(text: str) -> str:
    """Classify a user message into one of the known intents, else "other"."""
    msg_lower = " " + text.lower().strip() + " "

    has_possessive = any(marker in msg_lower for marker in _POSSESSIVE_MARKERS)
    if not has_possessive and any(trigger in msg_lower for trigger in _GLOSSARY_TRIGGERS):
        if find_glossary_term(text) is not None:
            return "financial_glossary"

    for intent, keywords in INTENT_KEYWORDS:
        if any(kw in msg_lower for kw in keywords):
            return intent
    return "other"
