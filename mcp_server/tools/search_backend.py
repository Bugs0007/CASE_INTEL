"""Case Bot retrieval for search_case_documents, owner-scoped.

Runs the existing VectorSearchService in this process (pgvector + tsvector,
fused by RRF) with `owner_id` -- the same scoping the Case Bot uses
(TestCaseBotRetrievalIsolation) -- and `use_reranker=False`: the MCP process
never loads the cross-encoder. Phase 0 measured the process at ~103 MB idle,
~147 MB after searches without it, and ~255 MB with it, against a 300 MB
MemoryMax. The service module is imported on the first search only; it
imports core.services.reranker's module (no model, no onnxruntime).
"""

from ..access import TenantContext

_service = None


def _get_service():
    global _service
    if _service is None:
        from core.services.vector_search_service import VectorSearchService

        _service = VectorSearchService(use_reranker=False)
    return _service


def search_chunks(ctx: TenantContext, query: str, *, case_id, top_k: int) -> list[dict]:
    (owner_id,) = tuple(ctx.owner_ids)  # one owner until organizations exist
    results = _get_service().search(query, owner_id=owner_id, case_id=case_id, top_k=top_k)
    return [
        {
            "document_id": r.chunk.document_id,
            "chunk_index": r.chunk.chunk_index,
            "text": r.chunk.chunk_text,
            "score": r.score,
        }
        for r in results
        if r.chunk.owner_id in ctx.owner_ids
    ]
