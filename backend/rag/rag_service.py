"""
Agent-facing RAG service.

This is what backend/voice_agent/realtime_agent.py's search_loan_knowledge
tool actually calls. It lazily loads the FAISS index once (not per
request, and not on every FastAPI/worker startup path that doesn't need
it) and formats retrieved chunks into a compact string for the model to
narrate — never raw embedding vectors, never whole documents.
"""

from __future__ import annotations

from backend.rag.retriever import DEFAULT_TOP_K, Retriever

_retriever: Retriever | None = None

NO_MATCH_MESSAGE = (
    "No sufficiently relevant information was found in the LoanMate knowledge base."
)


def _get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever.load()
    return _retriever


class RAGService:
    @staticmethod
    async def search(query: str, top_k: int = DEFAULT_TOP_K) -> str:
        """Search the knowledge base and return a compact, source-attributed
        text block for the agent to narrate, or an explicit "no match"
        message if nothing cleared the relevance threshold — the model is
        never left to fill that gap with an invented answer.
        """
        try:
            retriever = _get_retriever()
        except FileNotFoundError as e:
            return str(e)

        results = await retriever.retrieve(query, top_k=top_k)
        if not results:
            return NO_MATCH_MESSAGE

        parts = []
        for r in results:
            parts.append(f"[source: {r.source_file} — {r.section}]\n{r.text}")
        return "\n\n".join(parts)
