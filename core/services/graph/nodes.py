"""
LangGraph node implementations for the Case Intel AI workflow.

Redesigned to be a lean 3-node pipeline:

    OLD (6 LLM calls, 30-60 sec):
        query_router → query_analyzer → vector_search → chunk_ranker
        → answer_generator → citation_extractor → response_formatter

    NEW (2 LLM calls, 8-12 sec):
        hyde_expand → hybrid_search → generate_answer

Changes:
  - query_router + query_analyzer replaced by hyde_expand (1 LLM call).
    HyDE generates a hypothetical document that would answer the query,
    then embeds THAT instead of the raw question.  Closes the semantic
    gap between short questions and long legal document chunks.
  - chunk_ranker (LLM) replaced by cross-encoder inside VectorSearchService
    (pure Python, no Ollama call).
  - citation_extractor (LLM) replaced by inline span-matching in Python.
  - handle_no_results and handle_low_confidence merged into generate_answer
    via an explicit "cite-or-say-nothing" prompt.
  - response_formatter kept as lightweight Python post-processing.
"""

import logging
import re
from typing import Any

from core.services.graph import config
from core.services.graph.state import AgentState, ChunkData
from core.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_HYDE_SYSTEM = (
    "You are a legal document author. "
    "Write a short passage (3-5 sentences) that would directly answer the "
    "question below, as if it were extracted from a real legal document. "
    "Use formal legal language. Do NOT hedge or say you don't know — "
    "write the passage as if the facts are known."
)

_HYDE_USER = "Question: {query}\n\nWrite the passage:"

_ANSWER_SYSTEM = """You are a precise legal research assistant.
Answer the user's question using ONLY the document excerpts provided.

Rules:
1. Cite sources inline like [Doc 1], [Doc 2] matching the document labels.
2. Be factually precise: exact dates, amounts, party names, clause numbers.
3. If the excerpts do not contain enough information to answer confidently,
   say exactly: "I could not find that information in the uploaded documents."
   Do NOT guess or invent facts.
4. Keep the answer concise — use short paragraphs, not bullet points."""

_ANSWER_USER = """Question: {query}

Document excerpts:
{context}

Answer (cite sources inline):"""

# Appended to _ANSWER_SYSTEM only when the case has live tracking data.
# Untracked cases must see the exact original prompt.
_ANSWER_SYSTEM_TRACKING_ADDON = """

A "Live court tracking data" block is also provided. It comes from the
eCourts portal, NOT from any uploaded document.
5. For questions about hearing dates, case status, case stage, the judge,
   or the court, answer from that block and cite it inline as
   [Tracking Data].
6. NEVER cite a [Doc N] label for a fact that came from the tracking
   block, and never present a tracking fact as if it came from a document.
7. Rule 3's "not found in the uploaded documents" reply applies only when
   neither the excerpts nor the tracking block contain the answer."""

_TRACKING_BLOCK_TEMPLATE = """Live court tracking data ({source_label}):
{block}"""

_ANSWER_USER_WITH_TRACKING = """Question: {query}

{tracking_block}

Document excerpts:
{context}

Answer (cite sources inline):"""

# Used when retrieval returned no chunks but the case has tracking data —
# the old behaviour (canned "no documents found" reply, no LLM call) only
# remains for cases with neither chunks nor tracking data.
_ANSWER_USER_TRACKING_ONLY = """Question: {query}

{tracking_block}

No document excerpts were retrieved for this question. Answer ONLY if the
tracking data above contains the answer, citing it inline as
[Tracking Data]. Otherwise say exactly: "I could not find that information
in the uploaded documents or the court tracking data."

Answer:"""

_TRACKING_MARKER_RE = re.compile(r"\[Tracking\s+Data\]", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_context(chunks: list[ChunkData]) -> str:
    """Format retrieved chunks into a labelled context block for the LLM."""
    parts = []
    for i, chunk in enumerate(chunks):
        meta = chunk.get("metadata", {})
        filename = meta.get("filename", "Unknown")
        doc_type = meta.get("document_type", "")
        type_label = f" — {doc_type}" if doc_type else ""
        parts.append(
            f"[Doc {i + 1}: {filename}{type_label}]\n{chunk['text']}"
        )
    return "\n\n---\n\n".join(parts)


def _extract_citations_from_answer(
    answer: str,
    chunks: list[ChunkData],
) -> list[dict]:
    """Extract citations by matching [Doc N] markers in the answer.

    This replaces the LLM citation_extractor — pure Python, zero LLM calls.
    Scans the answer for [Doc 1], [Doc 2], … patterns and maps them back to
    the chunks list returned by hybrid_search.
    """
    citations = []
    seen_chunk_ids: set[int] = set()

    # Match all [Doc N] or [Document N] references in the answer
    for match in re.finditer(r'\[Doc(?:ument)?\s+(\d+)\]', answer, re.IGNORECASE):
        doc_num = int(match.group(1)) - 1  # 0-indexed
        if 0 <= doc_num < len(chunks):
            chunk = chunks[doc_num]
            chunk_id = chunk["chunk_id"]
            if chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(chunk_id)
                # Grab a short representative snippet from the chunk
                snippet = chunk["text"][:200].strip()
                citations.append({
                    "chunk_id": chunk_id,
                    "document_id": chunk["document_id"],
                    "citation_text": snippet,
                    "source_type": "chunk",
                })

    return citations


def _format_sources_section(
    answer: str,
    citations: list[dict],
    chunks: list[ChunkData],
    tracking_source_label: str | None = None,
) -> str:
    """Append a de-duplicated sources list to the answer.

    The tracking line is appended only when the answer actually cited
    [Tracking Data] — its presence in the prompt alone doesn't make it a
    source. It is labelled with the refresh timestamp (e.g. "eCourts
    tracking data (refreshed 19 Jul 2026, 17:06 UTC)"), never as a
    document.
    """
    tracking_used = bool(
        tracking_source_label and _TRACKING_MARKER_RE.search(answer)
    )
    if not citations and not tracking_used:
        return answer

    seen_doc_ids: set[int] = set()
    source_lines = ["\n\n**Sources:**"]

    for cit in citations:
        doc_id = cit["document_id"]
        if doc_id in seen_doc_ids:
            continue
        seen_doc_ids.add(doc_id)
        chunk = next((c for c in chunks if c["document_id"] == doc_id), None)
        if chunk:
            meta = chunk.get("metadata", {})
            filename = meta.get("filename", "Unknown")
            doc_type = meta.get("document_type", "")
            line = f"- {filename}"
            if doc_type:
                line += f" ({doc_type})"
            source_lines.append(line)

    if tracking_used:
        source_lines.append(f"- {tracking_source_label}")

    return answer + "\n".join(source_lines)


# ---------------------------------------------------------------------------
# Node 1: HyDE Expansion
# ---------------------------------------------------------------------------

def hyde_expand(state: AgentState, llm) -> AgentState:
    """Generate a hypothetical document excerpt and embed it as the search query.

    HyDE (Hypothetical Document Embeddings) closes the semantic gap between
    a short user question ("what was the settlement amount?") and long legal
    clauses ("the parties agreed to settle for ₹5,00,000 within 30 days…").

    The generated passage is stored in state["hyde_passage"] so the next
    node (hybrid_search) can embed it.  The original query is preserved.
    """
    query = state["user_query"]

    messages = [
        {"role": "system", "content": _HYDE_SYSTEM},
        {"role": "user", "content": _HYDE_USER.format(query=query)},
    ]

    try:
        hyde_passage = llm.generate(messages, temperature=0.3, max_tokens=200)
    except Exception:
        logger.warning("HyDE generation failed — falling back to raw query.", exc_info=True)
        hyde_passage = query

    state["hyde_passage"] = hyde_passage.strip()
    state["requires_clarification"] = False
    state["clarification_question"] = None
    # Determine a simple query type based on keywords (no LLM needed)
    lower = query.lower()
    if any(w in lower for w in ("summarize", "summary", "overview")):
        state["query_type"] = config.QUERY_TYPE_SUMMARIZE
    elif any(w in lower for w in ("compare", "difference", "versus", "vs")):
        state["query_type"] = config.QUERY_TYPE_COMPARE
    elif any(w in lower for w in ("timeline", "chronolog", "sequence", "when did")):
        state["query_type"] = config.QUERY_TYPE_TIMELINE
    else:
        state["query_type"] = config.QUERY_TYPE_SIMPLE_QA

    logger.info(
        "HyDE passage generated (%d chars), query_type=%s",
        len(state["hyde_passage"]),
        state["query_type"],
    )
    return state


# ---------------------------------------------------------------------------
# Node 2: Hybrid Search
# ---------------------------------------------------------------------------

def hybrid_search(state: AgentState, search_service: VectorSearchService) -> AgentState:
    """Run hybrid search using the HyDE passage (or raw query as fallback).

    VectorSearchService internally does:
        pgvector cosine search  +  tsvector keyword search
        → RRF fusion  →  cross-encoder rerank (no Ollama)

    The original user query is also passed for the keyword leg so that
    exact legal terms are captured even if the HyDE passage paraphrased them.
    """
    # Use HyDE passage for the vector leg (better semantic match)
    hyde_passage = state.get("hyde_passage") or state["user_query"]
    raw_query = state["user_query"]
    case_id = state.get("case_id")

    # Pass HyDE passage as the query — VectorSearchService will embed it
    # for the vector leg and use raw_query for the keyword leg internally.
    # We monkey-patch by passing both via a composite string; alternatively
    # expose a separate parameter.  Here we use the hybrid method directly.
    results = search_service.search(
        query=hyde_passage,              # vector leg uses HyDE embedding
        keyword_query=raw_query,         # keyword leg uses the original user query
        case_id=case_id,
        top_k=config.SEARCH_TOP_K,
    )

    # If HyDE found nothing, fall back to raw query so keyword search still works
    if not results:
        logger.info("HyDE search returned 0 results — retrying with raw query.")
        results = search_service.search(
            query=raw_query,
            case_id=case_id,
            top_k=config.SEARCH_TOP_K,
        )

    chunks: list[ChunkData] = []
    for r in results:
        d = r.to_dict()
        d["rerank_score"] = r.score  # already reranked inside the service
        chunks.append(d)

    state["retrieved_chunks"] = chunks
    state["chunk_count"] = len(chunks)
    state["search_confidence"] = chunks[0]["score"] if chunks else 0.0

    logger.info(
        "Hybrid search: %d chunks retrieved, top_score=%.4f",
        len(chunks),
        state["search_confidence"],
    )
    return state


# ---------------------------------------------------------------------------
# Node 3: Answer Generator (with inline citations)
# ---------------------------------------------------------------------------

def generate_answer(state: AgentState, llm) -> AgentState:
    """Generate an answer, extract citations, and format the final response.

    Combines the old answer_generator + citation_extractor + response_formatter
    into a single node to avoid redundant passes over the same data.

    If no chunks were retrieved, returns the standard "not found" message
    without any LLM call.
    """
    query = state["user_query"]
    chunks = state["retrieved_chunks"]
    tracking = state.get("tracking_context")
    tracking_block = (
        _TRACKING_BLOCK_TEMPLATE.format(
            source_label=tracking["source_label"], block=tracking["block"]
        )
        if tracking
        else None
    )

    # --- No results: skip LLM entirely (unless tracking data can answer) ---
    if not chunks and not tracking_block:
        case_id = state.get("case_id")
        if case_id:
            message = (
                "I could not find any documents relevant to your question in this case.\n\n"
                "Suggestions:\n"
                "- Make sure all relevant documents are uploaded and processed.\n"
                "- Try rephrasing your question using different keywords.\n"
                "- Check if the information is in a different case."
            )
        else:
            message = (
                "I could not find relevant documents for your question.\n\n"
                "Suggestions:\n"
                "- Select a specific case before asking.\n"
                "- Upload and process the relevant documents first."
            )
        state["answer"] = message
        state["citations"] = []
        state["answer_confidence"] = 0.0
        state["requires_clarification"] = False
        state["clarification_question"] = None
        return state

    # --- Build prompt ---
    # The tracking block (when present) is ALWAYS in the prompt — it is
    # injected structured data, never subject to retrieval — and always
    # kept separate from the retrieved excerpts so the model can't
    # attribute a live-portal fact to a document.
    system_prompt = _ANSWER_SYSTEM
    if tracking_block:
        system_prompt += _ANSWER_SYSTEM_TRACKING_ADDON

    if not chunks:
        user_content = _ANSWER_USER_TRACKING_ONLY.format(
            query=query, tracking_block=tracking_block
        )
    elif tracking_block:
        user_content = _ANSWER_USER_WITH_TRACKING.format(
            query=query,
            tracking_block=tracking_block,
            context=_build_context(chunks),
        )
    else:
        user_content = _ANSWER_USER.format(query=query, context=_build_context(chunks))

    # Include conversation history for follow-up awareness
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for msg in state.get("conversation_history", [])[-config.MAX_CONVERSATION_HISTORY:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_content})

    answer = llm.generate(
        messages,
        temperature=config.LLM_TEMPERATURE,
        max_tokens=config.LLM_MAX_TOKENS,
    )

    # --- Inline citation extraction (no LLM call) ---
    citations = _extract_citations_from_answer(answer, chunks)

    # --- Low confidence disclaimer (no LLM call) ---
    # Skipped for answers sourced purely from tracking data ([Tracking
    # Data] cited, no document citations) — the excerpt-coverage warning
    # is about retrieval quality and would be misleading there.
    tracking_only_answer = bool(
        tracking_block and _TRACKING_MARKER_RE.search(answer) and not citations
    )
    if state["search_confidence"] < config.CONFIDENCE_THRESHOLD and not tracking_only_answer:
        disclaimer = (
            "**Note:** The retrieved excerpts may not fully cover this topic. "
            "Please verify the answer against the original documents.\n\n"
        )
        answer = disclaimer + answer

    # --- Format sources section (no LLM call) ---
    answer = _format_sources_section(
        answer,
        citations,
        chunks,
        tracking_source_label=tracking["source_label"] if tracking else None,
    )

    # --- Confidence heuristic ---
    word_count = len(answer.split())
    if tracking_only_answer:
        # Answered from live structured portal data, not retrieval — the
        # retrieval-based factors below would misreport this as low
        # confidence.
        confidence = 0.9
    else:
        confidence = (
            state["search_confidence"] * 0.5
            + min(state["chunk_count"] / 5, 1.0) * 0.3
            + min(word_count / 100, 1.0) * 0.2
        )

    state["answer"] = answer
    state["citations"] = citations
    state["answer_confidence"] = round(confidence, 3)
    state["requires_clarification"] = False
    state["clarification_question"] = None

    logger.info(
        "Answer generated: %d words, %d citations, confidence=%.3f",
        word_count,
        len(citations),
        confidence,
    )
    return state
