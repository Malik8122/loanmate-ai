"""
Deterministic RAG evaluation set (see docs/LOANMATE_COMPLETE_DOCUMENTATION.md
"Testing" section for narrative results).

Each case is either:
  - a retrieval case: the question should retrieve a chunk from the given
    expected_source file as its top result, above the relevance threshold; or
  - a tool-routing case: the question should NOT trigger RAG at all — it
    is customer-specific and belongs to an existing deterministic tool
    (get_emi, calculate_prepayment, etc.), so expected_source is None and
    expect_no_retrieval is True.

Run directly:  python -m backend.rag.eval_set
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.rag.retriever import Retriever


@dataclass(frozen=True)
class EvalCase:
    question: str
    expected_source: str | None
    expect_no_retrieval: bool = False
    note: str = ""


EVAL_CASES: list[EvalCase] = [
    EvalCase("What documents are required for a personal loan?", "required_documents.md"),
    EvalCase("What is the prepayment policy?", "prepayment_policy.md"),
    EvalCase("What happens if I miss an EMI?", "missed_emi_policy.md"),
    EvalCase("Tell me about personal loans.", "personal_loan.md"),
    EvalCase("What is foreclosure?", "foreclosure_policy.md"),
    EvalCase(
        "What is my EMI?", None, expect_no_retrieval=True,
        note="Customer-specific — must route to get_emi, NOT RAG.",
    ),
    EvalCase(
        "What is my outstanding balance?", None, expect_no_retrieval=True,
        note="Customer-specific — must route to get_outstanding_balance, NOT RAG.",
    ),
    EvalCase(
        "If I prepay two lakh, what happens and is there a charge?",
        "prepayment_policy.md",
        note="Hybrid case — also expects calculate_prepayment to fire in the "
             "live agent; this eval only checks the RAG half (the charge question).",
    ),
    # Public RBI / Government knowledge
    EvalCase("Can the bank charge me for closing my floating rate home loan early?", "rbi_prepayment_foreclosure_rules.md"),
    EvalCase("Is penal interest allowed on a missed EMI?", "rbi_penal_charges.md"),
    EvalCase("What is a Key Fact Statement and APR?", "rbi_key_fact_statement.md"),
    EvalCase("The repo rate changed, when will my EMI change?", "rbi_interest_rate_benchmarks_and_reset.md"),
    EvalCase("How many days does the bank have to return my property papers after closing the loan?", "rbi_document_return_after_closure.md"),
    EvalCase("Can a recovery agent call me late at night?", "rbi_recovery_and_npa_rules.md"),
    EvalCase("Which documents are accepted for KYC?", "rbi_kyc_norms.md"),
    EvalCase("How do I complain to the RBI ombudsman?", "grievance_and_rbi_ombudsman.md"),
    EvalCase("Someone asked for my OTP, what should I do?", "fraud_safety.md"),
    EvalCase("How can I get my free credit report?", "credit_score_and_bureaus.md"),
    EvalCase("Am I eligible for the PMAY home loan subsidy?", "pmay_urban_2_interest_subsidy.md"),
    EvalCase("Is there a tax deduction on education loan interest?", "education_loan_schemes.md", note="Its tax section and loan_tax_benefits.md both answer this."),
    EvalCase("Can I claim home loan interest under the new tax regime?", "loan_tax_benefits.md"),
    EvalCase("What is a top-up loan?", "top_up_loan.md"),
    EvalCase("What is the LTV for a gold loan?", "gold_loan.md"),
    EvalCase("Can I settle my overdue loan for a lower amount?", "rbi_compromise_settlement.md"),
    EvalCase("Can I pay my EMI through UPI AutoPay?", "rbi_emi_payment_modes.md"),
    EvalCase("How do I transfer my home loan to another bank?", "home_loan_balance_transfer.md"),
    EvalCase("Is it compulsory to buy insurance with my home loan?", "loan_insurance_and_mis_selling.md"),
    EvalCase("What rights do I have as a bank customer?", "rbi_charter_of_customer_rights.md"),
]


async def run_eval() -> bool:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    retriever = Retriever.load()
    all_passed = True

    for case in EVAL_CASES:
        results = await retriever.retrieve(case.question, top_k=3)

        if case.expect_no_retrieval:
            # This eval set only checks the retrieval layer in isolation.
            # Whether the LIVE AGENT correctly chooses a deterministic tool
            # instead of calling search_loan_knowledge is a separate,
            # agent-level routing test (see docs — verified via live
            # simulated-conversation testing, not this script).
            print(f"[SKIP-ROUTING] {case.question!r} — {case.note}")
            continue

        top_source = results[0].source_file if results else None
        passed = top_source == case.expected_source
        all_passed = all_passed and passed
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {case.question!r}")
        print(f"         expected={case.expected_source}  got={top_source}"
              f"  score={results[0].score:.3f}" if results else f"         expected={case.expected_source}  got=NO RESULTS")

    return all_passed


if __name__ == "__main__":
    import asyncio

    ok = asyncio.run(run_eval())
    print("\nALL RETRIEVAL CASES PASSED" if ok else "\nSOME RETRIEVAL CASES FAILED")
