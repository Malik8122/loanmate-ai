"""
Splits a loaded knowledge document into semantic chunks — one chunk per
markdown "## " section, not a blind fixed-character split. Each of the
knowledge base's .md files was written with meaningful section headings
(Overview, Eligibility Criteria, Charges, Frequently Asked Questions,
etc.), so splitting on those headings keeps each chunk topically coherent
and gives the retriever a real section name to attach as metadata.

A defensive max-length fallback further splits any single section that
is unusually long, so no chunk sent to the embedding model is huge —
this does not trigger on the current knowledge base (every section is a
few short paragraphs), but keeps the chunker correct if a much longer
document is added later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.rag.document_loader import RawDocument

_MAX_CHUNK_CHARS = 1200
_H1_RE = re.compile(r"^#\s+.*$", re.MULTILINE)
_H2_SPLIT_RE = re.compile(r"^##\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str
    source_file: str
    document_type: str
    topic: str
    section: str

    def to_metadata(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "source_file": self.source_file,
            "document_type": self.document_type,
            "topic": self.topic,
            "section": self.section,
        }


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) + 2 > max_chars:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        parts.append(current)
    return parts or [text]


def chunk_document(doc: RawDocument) -> list[Chunk]:
    """Split one document into (section_name, section_body) pairs on '## '
    headings, then into Chunk objects with full metadata.
    """
    body = _H1_RE.sub("", doc.text, count=1).strip()

    # Everything before the first "## " heading is the document's overview
    # (title/intro line + any lead-in paragraph, including the demo-content
    # disclaimer blockquote).
    first_h2 = _H2_SPLIT_RE.search(body)
    sections: list[tuple[str, str]] = []
    if first_h2 is None:
        sections.append(("Overview", body.strip()))
    else:
        overview = body[: first_h2.start()].strip()
        if overview:
            sections.append(("Overview", overview))
        headings = _H2_SPLIT_RE.findall(body)
        bodies = _H2_SPLIT_RE.split(body)[1:]  # alternating [heading, body, heading, body, ...]
        section_bodies = bodies[1::2]
        for heading, section_body in zip(headings, section_bodies):
            sections.append((heading.strip(), section_body.strip()))

    chunks: list[Chunk] = []
    seq = 0
    for section_name, section_text in sections:
        if not section_text:
            continue
        for part in _split_long_text(section_text, _MAX_CHUNK_CHARS):
            seq += 1
            chunk_id = f"{doc.topic}_{seq:02d}"
            full_text = f"{doc.title} — {section_name}\n\n{part}"
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=full_text,
                    source_file=doc.source_file,
                    document_type=doc.document_type,
                    topic=doc.topic,
                    section=section_name,
                )
            )
    return chunks


def chunk_documents(docs: list[RawDocument]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for doc in docs:
        chunks.extend(chunk_document(doc))
    return chunks


if __name__ == "__main__":
    from backend.rag.document_loader import load_documents

    all_chunks = chunk_documents(load_documents())
    print(f"Produced {len(all_chunks)} chunks")
    for c in all_chunks[:5]:
        print(f"  {c.chunk_id} [{c.section}] ({len(c.text)} chars)")
