"""
LangGraph node implementations for the Case Intel AI workflow.

Each function is a graph node that receives the shared AgentState,
performs its step, and returns the updated state. Nodes are stateless;
all shared data flows through AgentState.
"""

import json
import logging
from collections import Counter
from typing import Any

from core.services.graph import config
from core.services.graph.state import AgentState, ChunkData
from core.services.llm_client import LLMClient
from core.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_ROUTER_SYSTEM = (
    "You are a query classifier for a legal research system. "
    "Analyze the user's question and classify it."
)

_ROUTER_USER = """Analyze this legal question and determine:

Question: {query}

Classify as one of:
1. simple_qa - Straightforward question about documents
2. summarize - Requesting summary of document(s)
3. compare - Comparing multiple documents or arguments
4. timeline - Requesting chronological sequence
5. unclear - Question is too vague to process

Also determine if clarification is needed (true/false).

Respond ONLY with valid JSON:
{{
    "query_type": "...",
    "needs_clarification": true or false,
    "clarification_question": "..." or null
}}"""

_ANALYZER_SYSTEM = (
    "You are a legal query analyzer. Extract structured search parameters "
    "from the user's question. Respond only with valid JSON."
)

_ANALYZER_USER = """Extract search parameters from this legal question:

Question: {query}
Current Case Context: {case_context}

Extract:
1. Document types mentioned (motion, brief, pleading, evidence, contract, correspondence, order, other)
2. Date ranges (if any)
3. Key entities (people, organizations)
4. Specific document references

Respond ONLY with valid JSON:
{{
    "document_types": [],
    "date_range": {{"start": null, "end": null}},
    "entities": [],
    "specific_docs": []
}}"""


_QA_SYSTEM = """You are a legal research assistant. Answer the question based ONLY on the provided document excerpts.

Rules:
1. Be precise and factual
2. Cite specific documents when making claims
3. If information is not in the excerpts, say so
4. Use legal terminology appropriately
5. Do not speculate or infer beyond what's stated"""

_SUMMARIZE_SYSTEM = (
    "You are a legal research assistant. Summarize the key points from "
    "the provided documents. Be concise and highlight the most important facts."
)

_COMPARE_SYSTEM = (
    "You are a legal research assistant. Compare and contrast the provided "
    "documents. Highlight similarities and differences clearly."
)

_TIMELINE_SYSTEM = (
    "You are a legal research assistant. Create a chronological timeline "
    "from the provided documents. List events with dates when available."
)

_ANSWER_USER = """Question: {query}

Context from case documents:
{context}

Provide a clear, well-structured answer."""

_CITATION_SYSTEM = (
    "You are a citation extraction system. Map claims in the answer "
    "to their supporting source chunks. Respond only with valid JSON."
)

_CITATION_USER = """Given this answer and source chunks, identify which chunks support each claim.

Answer:
{answer}

Source Chunks:
{chunks_text}

For each significant claim in the answer, identify supporting chunks.

Respond ONLY with valid JSON:
{{
    "citations": [
        {{
            "answer_text": "the specific claim...",
            "chunk_indices": [0, 2],
            "quote": "exact short quote from the chunk"
        }}
    ]
}}"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_json_safe(text: str) -> dict[str, Any]:
    """Parse JSON from LLM response, handling markdown code fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Strip ```json ... ``` wrappers
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM JSON response: %s...", cleaned[:200])
        return {}


def _build_context(chunks: list[ChunkData]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    parts = []
    for i, chunk in enumerate(chunks):
        filename = chunk.get("metadata", {}).get("filename", "Unknown")
        parts.append(f"[Document {i + 1}: {filename}]\n{chunk['text']}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Node 1: Query Router
# ---------------------------------------------------------------------------

def query_router(state: AgentState, llm: LLMClient) -> AgentState:
    """Classify the query type and determine if clarification is needed."""
    query = state["user_query"]

    messages = [
        {"role": "system", "content": _ROUTER_SYSTEM},
        {"role": "user", "content": _ROUTER_USER.format(query=query)},
    ]

    raw = llm.generate_with_json(messages, temperature=0.0)
    result = _parse_json_safe(raw)

    query_type = result.get("query_type", config.QUERY_TYPE_SIMPLE_QA)
    if query_type not in config.VALID_QUERY_TYPES:
        query_type = config.QUERY_TYPE_SIMPLE_QA

    needs_clarification = result.get("needs_clarification", False)

    state["query_type"] = query_type
    state["requires_clarification"] = bool(needs_clarification)
    state["clarification_question"] = result.get("clarification_question")

    logger.info(
        "Query routed: type=%s, needs_clarification=%s",
        query_type,
        needs_clarification,
    )
    return state


# ---------------------------------------------------------------------------
# Node 2: Query Analyzer
# ---------------------------------------------------------------------------

def query_analyzer(state: AgentState, llm: LLMClient) -> AgentState:
    """Extract structured search parameters from the query."""
    query = state["user_query"]
    case_id = state.get("case_id")

    case_context = f"Case ID {case_id}" if case_id else "None specified"

    messages = [
        {"role": "system", "content": _ANALYZER_SYSTEM},
        {
            "role": "user",
            "content": _ANALYZER_USER.format(
                query=query, case_context=case_context
            ),
        },
    ]

    raw = llm.generate_with_json(messages, temperature=0.0)
    filters = _parse_json_safe(raw)

    state["extracted_filters"] = {
        "document_types": filters.get("document_types", []),
        "date_range": filters.get("date_range", {}),
        "entities": filters.get("entities", []),
        "specific_docs": filters.get("specific_docs", []),
    }

    logger.info("Query analyzed: filters=%s", state["extracted_filters"])
    return state


# ---------------------------------------------------------------------------
# Node 3: Vector Search
# ---------------------------------------------------------------------------

def vector_search(state: AgentState, search_service: VectorSearchService) -> AgentState:
    """Retrieve relevant document chunks from pgvector."""
    query = state["user_query"]
    case_id = state.get("case_id")

    # Don't filter by document types - just search all documents in case
    # Document type filtering causes false negatives when document_type doesn't match
    doc_types = None

    results = search_service.search(
        query=query,
        case_id=case_id,
        document_types=doc_types,
        top_k=config.SEARCH_TOP_K,
    )

    chunks: list[ChunkData] = []
    for r in results:
        chunk_dict = r.to_dict()
        chunk_dict["rerank_score"] = 0.0
        chunks.append(chunk_dict)

    state["retrieved_chunks"] = chunks
    state["chunk_count"] = len(chunks)
    state["search_confidence"] = chunks[0]["score"] if chunks else 0.0

    logger.info(
        "Vector search: found %d chunks, top_score=%.3f",
        len(chunks),
        state["search_confidence"],
    )
    return state


# ---------------------------------------------------------------------------
# Node 4: Chunk Ranker
# ---------------------------------------------------------------------------

def chunk_ranker(state: AgentState, llm: LLMClient) -> AgentState:
    """Re-rank chunks by relevance using an LLM-based scoring approach.

    Also deduplicates by limiting chunks per document.
    """
    query = state["user_query"]
    chunks = state["retrieved_chunks"]

    if not chunks:
        return state

    # Use LLM to score relevance of each chunk
    scoring_prompt = (
        "Rate the relevance of each document excerpt to the question on a scale of 0-10.\n\n"
        f"Question: {query}\n\n"
    )
    for i, chunk in enumerate(chunks):
        scoring_prompt += f"Excerpt {i}: {chunk['text'][:300]}...\n\n"

    scoring_prompt += (
        "Respond ONLY with valid JSON: {\"scores\": [score_for_0, score_for_1, ...]}"
    )

    messages = [
        {"role": "system", "content": "You are a relevance scoring system. Rate document relevance."},
        {"role": "user", "content": scoring_prompt},
    ]

    raw = llm.generate_with_json(messages, temperature=0.0)
    result = _parse_json_safe(raw)
    scores = result.get("scores", [])

    # Apply rerank scores
    for i, chunk in enumerate(chunks):
        if i < len(scores):
            try:
                chunk["rerank_score"] = float(scores[i])
            except (ValueError, TypeError):
                chunk["rerank_score"] = chunk["score"] * 10
        else:
            chunk["rerank_score"] = chunk["score"] * 10

    # Sort by rerank score descending
    chunks.sort(key=lambda c: c["rerank_score"], reverse=True)

    # Take top K
    chunks = chunks[: config.RERANK_TOP_K]

    # Deduplicate: limit chunks per document
    doc_counter: Counter[int] = Counter()
    deduped: list[ChunkData] = []
    for chunk in chunks:
        doc_id = chunk["document_id"]
        if doc_counter[doc_id] < config.MAX_CHUNKS_PER_DOCUMENT:
            deduped.append(chunk)
            doc_counter[doc_id] += 1

    state["retrieved_chunks"] = deduped
    state["chunk_count"] = len(deduped)

    logger.info(
        "Chunks re-ranked: %d -> %d after deduplication",
        len(chunks),
        len(deduped),
    )
    return state


# ---------------------------------------------------------------------------
# Node 5: Answer Generator
# ---------------------------------------------------------------------------

_SYSTEM_PROMPTS = {
    config.QUERY_TYPE_SIMPLE_QA: _QA_SYSTEM,
    config.QUERY_TYPE_SUMMARIZE: _SUMMARIZE_SYSTEM,
    config.QUERY_TYPE_COMPARE: _COMPARE_SYSTEM,
    config.QUERY_TYPE_TIMELINE: _TIMELINE_SYSTEM,
}


def answer_generator(state: AgentState, llm: LLMClient) -> AgentState:
    """Generate an answer using the LLM with retrieved chunks as context."""
    query = state["user_query"]
    chunks = state["retrieved_chunks"]
    query_type = state.get("query_type", config.QUERY_TYPE_SIMPLE_QA)

    context = _build_context(chunks)
    system_prompt = _SYSTEM_PROMPTS.get(query_type, _QA_SYSTEM)

    # Include conversation history if available
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    history = state.get("conversation_history", [])
    for msg in history[-config.MAX_CONVERSATION_HISTORY :]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({
        "role": "user",
        "content": _ANSWER_USER.format(query=query, context=context),
    })

    answer = llm.generate(
        messages,
        temperature=config.LLM_TEMPERATURE,
        max_tokens=config.LLM_MAX_TOKENS,
    )

    # Compute confidence heuristic
    word_count = len(answer.split())
    confidence = (
        state["search_confidence"] * 0.4
        + min(state["chunk_count"] / 5, 1.0) * 0.3
        + min(word_count / 100, 1.0) * 0.3
    )

    state["answer"] = answer
    state["answer_confidence"] = round(confidence, 3)

    logger.info(
        "Answer generated: %d words, confidence=%.3f",
        word_count,
        confidence,
    )
    return state


# ---------------------------------------------------------------------------
# Node 6: Citation Extractor
# ---------------------------------------------------------------------------

def citation_extractor(state: AgentState, llm: LLMClient) -> AgentState:
    """Map answer claims to source chunks for citation tracking."""
    answer = state["answer"]
    chunks = state["retrieved_chunks"]

    if not chunks:
        state["citations"] = []
        return state

    chunks_text = "\n".join(
        f"Chunk {i} (from {c.get('metadata', {}).get('filename', 'Unknown')}): "
        f"{c['text'][:300]}..."
        for i, c in enumerate(chunks)
    )

    messages = [
        {"role": "system", "content": _CITATION_SYSTEM},
        {
            "role": "user",
            "content": _CITATION_USER.format(
                answer=answer, chunks_text=chunks_text
            ),
        },
    ]

    raw = llm.generate_with_json(messages, temperature=0.0)
    result = _parse_json_safe(raw)

    citations = []
    seen = set()

    for citation in result.get("citations", []):
        for chunk_idx in citation.get("chunk_indices", []):
            if chunk_idx < len(chunks) and chunk_idx not in seen:
                seen.add(chunk_idx)
                chunk = chunks[chunk_idx]
                citations.append({
                    "chunk_id": chunk["chunk_id"],
                    "document_id": chunk["document_id"],
                    "citation_text": citation.get("quote", chunk["text"][:200]),
                    "source_type": "chunk",
                })

    state["citations"] = citations
    logger.info("Citations extracted: %d", len(citations))
    return state


# ---------------------------------------------------------------------------
# Node 7: Response Formatter
# ---------------------------------------------------------------------------

def response_formatter(state: AgentState) -> AgentState:
    """Format the final response with a sources section."""
    answer = state["answer"]
    citations = state.get("citations", [])
    chunks = state.get("retrieved_chunks", [])

    if not citations:
        return state

    # Group citations by document
    docs_cited: dict[int, dict] = {}
    for citation in citations:
        doc_id = citation["document_id"]
        if doc_id in docs_cited:
            continue

        chunk = next((c for c in chunks if c["document_id"] == doc_id), None)
        if chunk:
            meta = chunk.get("metadata", {})
            docs_cited[doc_id] = {
                "filename": meta.get("filename", "Unknown"),
                "document_type": meta.get("document_type", ""),
            }

    # Build sources section
    sources_lines = ["\n\n**Sources:**"]
    for doc in docs_cited.values():
        line = f"- {doc['filename']}"
        if doc["document_type"]:
            line += f" ({doc['document_type']})"
        sources_lines.append(line)

    state["answer"] = answer + "\n".join(sources_lines)
    return state


# ---------------------------------------------------------------------------
# Node 8: Handle No Results
# ---------------------------------------------------------------------------

def handle_no_results(state: AgentState) -> AgentState:
    """Generate a helpful response when no relevant documents are found."""
    case_id = state.get("case_id")

    if case_id:
        message = (
            "I couldn't find any documents relevant to your question in this case.\n\n"
            "Possible reasons:\n"
            "1. The information might not be in the uploaded documents\n"
            "2. Try rephrasing your question\n"
            "3. Check if all relevant documents are uploaded\n\n"
            "Would you like to rephrase your question or search in a different case?"
        )
    else:
        message = (
            "I couldn't find relevant documents for your question.\n\n"
            "Try:\n"
            "1. Selecting a specific case\n"
            "2. Uploading relevant documents first\n"
            "3. Rephrasing your question"
        )

    state["answer"] = message
    state["citations"] = []
    state["answer_confidence"] = 0.0
    return state


# ---------------------------------------------------------------------------
# Node 9: Handle Low Confidence
# ---------------------------------------------------------------------------

def handle_low_confidence(state: AgentState, llm: LLMClient) -> AgentState:
    """Generate an answer with a low-confidence disclaimer."""
    state = answer_generator(state, llm)

    disclaimer = (
        "**Note:** I found some potentially relevant documents, but I'm not "
        "highly confident this fully answers your question. Please verify "
        "the information against the original documents.\n\n"
    )
    state["answer"] = disclaimer + state["answer"]
    return state
