"""
Gemini embedding wrapper for the RAG pipeline.

Uses the currently supported `google-genai` SDK (already a project
dependency, pulled in by `livekit-agents[google]`) — NOT the deprecated
`google-generativeai` SDK that backend/services/llm_service.py still uses
for the legacy text-chat path. That legacy usage is left untouched.

Model: gemini-embedding-2, confirmed available for this project's real
GOOGLE_API_KEY via a live models.list() call (see docs for the exact
verification). output_dimensionality is truncated to 768 (a supported
Matryoshka-style truncation of the model's native 3072-dim output) to
keep the local FAISS index small — verified working via a real API call
before being adopted here, not assumed.

Uses separate task types for indexing vs. querying (RETRIEVAL_DOCUMENT /
RETRIEVAL_QUERY), which is Gemini's documented mechanism for asymmetric
retrieval embeddings — a document chunk and a short question are
embedded slightly differently so they compare well against each other.

Batch embedding (passing a list of strings to `contents`) was tested and
found to silently return fewer embeddings than inputs, which would
misalign chunk text and metadata — so embeddings are requested one text
at a time instead, which is safe and, for this project's small (~75
chunk) knowledge base, fast enough for an offline ingest step.

Query-time embedding uses the SDK's async client (`client.aio.models.
embed_content`) rather than the sync client wrapped in
`asyncio.to_thread()`. This matters specifically because the realtime
agent's search_loan_knowledge tool runs concurrently with a live Gemini
Live audio session on the same asyncio event loop: a live measurement
during development showed the sync-client-in-a-thread version taking
6.5-8.6 seconds per call inside the live agent (vs. ~0.5-0.8s for the
same call made in an isolated script), consistent with the worker
thread being starved of scheduling time while the event loop is busy
streaming audio. The async client instead awaits the network I/O
directly on the event loop, without a thread hop, and removes that
contention.
"""

from __future__ import annotations

from google import genai
from google.genai import types as genai_types

from backend.config import settings

EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GOOGLE_API_KEY)
    return _client


def embed_document(text: str) -> list[float]:
    """Embed one knowledge-base chunk for indexing (offline, synchronous —
    used only by backend/rag/ingest.py, which has no event loop to protect).
    """
    resp = _get_client().models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    return list(resp.embeddings[0].values)


async def embed_query(text: str) -> list[float]:
    """Embed a user's search query at retrieval time — async, so it never
    blocks the realtime agent's event loop (see module docstring).
    """
    resp = await _get_client().aio.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=genai_types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=EMBEDDING_DIMENSIONS,
        ),
    )
    return list(resp.embeddings[0].values)
