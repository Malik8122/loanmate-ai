"""
Loads LoanMate's demo knowledge base from backend/knowledge/*.md.

Each document's "document_type" is taken from its parent folder name
(loan_products, policies, faq, documents) and its "topic" from the
filename — this is plain filesystem convention, not a classifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"


@dataclass(frozen=True)
class RawDocument:
    source_file: str       # e.g. "personal_loan.md"
    document_type: str     # e.g. "loan_products"
    topic: str             # e.g. "personal_loan"
    title: str             # first H1 heading in the file, or the filename
    text: str              # full raw markdown text


def _extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def load_documents(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[RawDocument]:
    """Recursively load every .md file under knowledge_dir."""
    if not knowledge_dir.exists():
        raise FileNotFoundError(f"Knowledge base directory not found: {knowledge_dir}")

    documents: list[RawDocument] = []
    for md_path in sorted(knowledge_dir.rglob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        document_type = md_path.parent.name
        topic = md_path.stem
        title = _extract_title(text, fallback=topic)
        documents.append(
            RawDocument(
                source_file=md_path.name,
                document_type=document_type,
                topic=topic,
                title=title,
                text=text,
            )
        )
    return documents


if __name__ == "__main__":
    docs = load_documents()
    print(f"Loaded {len(docs)} documents from {KNOWLEDGE_DIR}")
    for d in docs:
        print(f"  [{d.document_type}] {d.source_file} — {d.title}")
