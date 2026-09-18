"""
Local, file-based vector store for the RAG pipeline, backed by FAISS.

Uses a flat (exact, brute-force) index — `IndexFlatIP` over L2-normalized
vectors, which makes inner product equivalent to cosine similarity. An
approximate/ANN index (HNSW, IVF, etc.) was deliberately NOT used: the
knowledge base is small (75 chunks as of this writing), so an exact
search is both fast enough (well under a millisecond) and gives exact
— not approximate — nearest neighbours, which is the more honest choice
at this scale. This is a genuine FAISS vector index, not a hand-rolled
substitute, but it should be described precisely as a flat/exact index
rather than an ANN index like HNSW.

No paid or hosted vector database is used — everything here is two local
files (a FAISS index and a JSON metadata sidecar), suitable for shipping
alongside the application in a free-tier deployment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

VECTOR_STORE_DIR = Path(__file__).resolve().parent / "vector_store"
INDEX_PATH = VECTOR_STORE_DIR / "loanmate.index"
METADATA_PATH = VECTOR_STORE_DIR / "metadata.json"


@dataclass(frozen=True)
class StoredChunk:
    text: str
    metadata: dict


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class VectorStore:
    def __init__(self, index: "faiss.Index", chunks: list[StoredChunk]):
        self._index = index
        self._chunks = chunks

    @property
    def size(self) -> int:
        return len(self._chunks)

    @property
    def dimensions(self) -> int:
        return self._index.d

    @classmethod
    def build(cls, vectors: list[list[float]], chunks: list[StoredChunk]) -> "VectorStore":
        if len(vectors) != len(chunks):
            raise ValueError("vectors and chunks must be the same length")
        matrix = _normalize(np.array(vectors, dtype="float32"))
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        return cls(index, chunks)

    def save(self, index_path: Path = INDEX_PATH, metadata_path: Path = METADATA_PATH) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(index_path))
        metadata_path.write_text(
            json.dumps([{"text": c.text, "metadata": c.metadata} for c in self._chunks], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, index_path: Path = INDEX_PATH, metadata_path: Path = METADATA_PATH) -> "VectorStore":
        if not index_path.exists() or not metadata_path.exists():
            raise FileNotFoundError(
                f"RAG index not found at {index_path}. Run `python -m backend.rag.ingest` first."
            )
        index = faiss.read_index(str(index_path))
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        chunks = [StoredChunk(text=r["text"], metadata=r["metadata"]) for r in raw]
        return cls(index, chunks)

    def search(self, query_vector: list[float], top_k: int) -> list[tuple[float, StoredChunk]]:
        """Returns up to top_k (cosine_similarity_score, StoredChunk) pairs,
        highest similarity first.
        """
        if self.size == 0:
            return []
        q = _normalize(np.array([query_vector], dtype="float32"))
        scores, indices = self._index.search(q, min(top_k, self.size))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            results.append((float(score), self._chunks[idx]))
        return results
