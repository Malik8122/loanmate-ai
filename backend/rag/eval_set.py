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
