"""
Build (or rebuild) the LoanMate RAG vector index from the knowledge base.

Run whenever backend/knowledge/*.md changes:

    python -m backend.rag.ingest

This is a one-time/offline step — the realtime agent and FastAPI backend
only ever LOAD the resulting index files (backend/rag/vector_store/
loanmate.index + metadata.json); neither of them regenerates the index
at startup, so a normal run of the application makes no embedding API
calls at all.
"""

from __future__ import annotations

import sys
import time

from backend.rag.chunker import chunk_documents
from backend.rag.document_loader import load_documents
from backend.rag.embeddings import embed_document
from backend.rag.vector_store import StoredChunk, VectorStore

# The Gemini free tier allows 100 embedding requests per minute, and the
# knowledge base is larger than that — wait out a 429 instead of failing.
_RATE_LIMIT_WAIT_S = 45
_MAX_RETRIES = 5


def _embed_with_retry(text: str) -> list[float]:
    for attempt in range(_MAX_RETRIES):
        try:
            return embed_document(text)
        except Exception as e:  # google.genai.errors.ClientError carries .code
            if getattr(e, "code", None) != 429 or attempt == _MAX_RETRIES - 1:
                raise
            print(f"   Rate limited — waiting {_RATE_LIMIT_WAIT_S}s before retrying...")
            time.sleep(_RATE_LIMIT_WAIT_S)
    raise RuntimeError("unreachable")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    print("1. Loading knowledge documents...")
    docs = load_documents()
    print(f"   Loaded {len(docs)} documents.")

    print("2. Chunking documents into semantic sections...")
    chunks = chunk_documents(docs)
    print(f"   Produced {len(chunks)} chunks.")

    print("3. Generating embeddings (gemini-embedding-2, one call per chunk)...")
    t0 = time.monotonic()
    vectors: list[list[float]] = []
    stored_chunks: list[StoredChunk] = []
    for i, chunk in enumerate(chunks, start=1):
        vector = _embed_with_retry(chunk.text)
        vectors.append(vector)
        stored_chunks.append(StoredChunk(text=chunk.text, metadata=chunk.to_metadata()))
        print(f"   [{i}/{len(chunks)}] embedded {chunk.chunk_id}")
    embed_ms = (time.monotonic() - t0) * 1000
    print(f"   Done in {embed_ms:.0f}ms ({embed_ms / len(chunks):.0f}ms/chunk average).")

    print("4. Building FAISS vector index...")
    store = VectorStore.build(vectors, stored_chunks)
    print(f"   Index built: {store.size} vectors, {store.dimensions} dimensions.")

    print("5. Saving index and metadata...")
    store.save()
    from backend.rag.vector_store import INDEX_PATH, METADATA_PATH
    print(f"   Saved: {INDEX_PATH}")
    print(f"   Saved: {METADATA_PATH}")

    print("\nIngestion complete.")


if __name__ == "__main__":
    main()
