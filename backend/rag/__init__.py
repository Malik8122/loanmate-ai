"""
Retrieval-Augmented Generation (RAG) module for LoanMate.

This is additive to the existing realtime voice architecture — it does not
replace Gemini Live, LiveKit, AgentSession, or any deterministic financial
tool. It adds one new capability: semantic search over a small, local
knowledge base of LoanMate demo policies/products/FAQs, exposed to the
realtime agent as a single tool (search_loan_knowledge).

Pipeline:
    backend/knowledge/*.md
        -> document_loader.load_documents()
        -> chunker.chunk_documents()
        -> embeddings.embed_query() / embed_document()   (Gemini embeddings)
        -> vector_store.VectorStore                       (FAISS, local, flat/exact index)
        -> retriever.Retriever.retrieve()
        -> rag_service.RAGService.search()                (used by the agent tool)

Build/rebuild the index with:  python -m backend.rag.ingest
"""
