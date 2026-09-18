"""
High-level semantic retrieval over the LoanMate knowledge base.

retrieve(query, top_k=3) embeds the query (RETRIEVAL_QUERY task type),
searches the local FAISS index, and filters out anything below
MIN_RELEVANCE_SCORE — chosen empirically by running the RAG evaluation
set (backend/rag/eval_set.py) against the real index and inspecting the
actual score distribution (see docs for the measured numbers), not
picked arbitrarily. This is what prevents the agent from receiving (and
therefore narrating) a retrieval result for an off-topic question.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.rag.embeddings import embed_query
from backend.rag.vector_store import StoredChunk, VectorStore

# Empirically derived by running backend/rag/eval_set.py's on-topic
# queries and a set of clearly off-topic queries against the real,
# built index and inspecting the actual cosine-similarity scores (see
# docs/LOANMATE_COMPLETE_DOCUMENTATION.md "RAG Performance" for the full
# table). Measured result: every on-topic query's best-matching chunk
# scored 0.713-0.860; every off-topic query's best-matching chunk (still
# some positive similarity, since all chunks share generic banking
# vocabulary) scored only 0.525-0.591. 0.65 sits in the empirical gap
# between those two clusters.
MIN_RELEVANCE_SCORE = 0.65
DEFAULT_TOP_K = 3


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    score: float
    source_file: str
    document_type: str
    topic: str
    section: str


class Retriever:
    def __init__(self, store: VectorStore):
        self._store = store

    @classmethod
    def load(cls) -> "Retriever":
        return cls(VectorStore.load())

    async def retrieve(
        self, query: str, top_k: int = DEFAULT_TOP_K, min_score: float = MIN_RELEVANCE_SCORE
    ) -> list[RetrievedChunk]:
        query_vector = await embed_query(query)
        raw_results = self._store.search(query_vector, top_k=top_k)

        results: list[RetrievedChunk] = []
        for score, chunk in raw_results:
            if score < min_score:
                continue
            results.append(
                RetrievedChunk(
                    text=chunk.text,
                    score=score,
                    source_file=chunk.metadata["source_file"],
                    document_type=chunk.metadata["document_type"],
                    topic=chunk.metadata["topic"],
                    section=chunk.metadata["section"],
                )
            )
        return results
