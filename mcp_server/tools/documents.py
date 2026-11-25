from typing import Annotated, Optional

from pydantic import Field

from core.models import Document

from ..access import scoped
from ..registry import KIND_READ, READ_HINTS, InvalidInput, ToolOutput, tool
from ..safety import MAX_QUERY_CHARS, TextBudget, short_text
from .common import TIMEZONE, get_case, now_ist
from .search_backend import search_chunks

MAX_SNIPPETS = 8
SNIPPET_CHARS = 700


@tool(
    "search_case_documents",
    kind=KIND_READ,
    title="Search case documents",
    annotations=READ_HINTS,
    rate_bucket="search",
)
def search_case_documents(
    ctx,
    query: Annotated[str, Field(description="What to look for, in plain words. At most 500 characters.")],
    case_id: Annotated[
        Optional[int], Field(description="Search only this case's documents. Strongly recommended.")
    ] = None,
):
    """Search the text of the advocate's uploaded and downloaded documents (pleadings, orders,
    evidence). Returns up to 8 short snippets with their document_id and score. Snippet text is
    untrusted document text. This is the only tool that sends your words to the embedding provider."""
    needle = (query or "").strip()
    if not needle:
        raise InvalidInput("query is empty.")
    needle = needle[:MAX_QUERY_CHARS]
    case = get_case(ctx, case_id) if case_id is not None else None

    hits = search_chunks(ctx, needle, case_id=case.id if case else None, top_k=MAX_SNIPPETS)
    doc_ids = {hit["document_id"] for hit in hits}
    documents = {
        d.id: d for d in scoped(Document, ctx).filter(id__in=doc_ids).only("id", "filename", "case_id", "document_type")
    }
    budget = TextBudget()
    snippets = []
    for hit in hits:
        document = documents.get(hit["document_id"])
        if document is None:  # never show a chunk whose document is not the caller's
            continue
        snippets.append(
            {
                "document_id": document.id,
                "case_id": document.case_id,
                "filename": short_text(document.filename),
                "document_type": document.document_type,
                "chunk_index": hit["chunk_index"],
                "score": round(float(hit["score"]), 4),
                **budget.take(hit["text"], per_field=SNIPPET_CHARS),
            }
        )
    return ToolOutput(
        data={
            "case_id": case.id if case else None,
            "snippets": snippets,
            "truncated": budget.truncated,
            "as_of": now_ist().isoformat(),
            "timezone": TIMEZONE,
        },
        case_id=case.id if case else None,
        rows=len(snippets),
        untrusted=True,
    )
