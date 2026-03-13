"""
LangGraph state schema for the Case Intel AI workflow.

Defines the typed state dict shared across all graph nodes.
"""

from typing import Optional, TypedDict


class ChunkData(TypedDict):
    """Serialized representation of a retrieved document chunk."""

    chunk_id: int
    document_id: int
    chunk_index: int
    text: str
    score: float
    rerank_score: float
    metadata: dict


class CitationData(TypedDict):
    """A citation linking an answer claim to a source chunk."""

    chunk_id: int
    document_id: int
    citation_text: str
    source_type: str


class AgentState(TypedDict):
    """Shared state passed through all LangGraph nodes.

    Every node reads from and writes to this state dict. Fields are
    grouped by the pipeline stage that primarily produces them.
    """

    # --- Input ---
    user_query: str
    case_id: Optional[int]
    conversation_id: Optional[int]
    conversation_history: list[dict]  # Previous messages [{role, content}]

    # --- Query Analysis ---
    query_type: str
    requires_clarification: bool
    clarification_question: Optional[str]
    extracted_filters: dict  # {document_types, date_range, entities, ...}

    # --- Search Results ---
    retrieved_chunks: list[ChunkData]
    chunk_count: int
    search_confidence: float

    # --- Answer Generation ---
    answer: str
    answer_confidence: float

    # --- Citations ---
    citations: list[CitationData]

    # --- Error Handling ---
    error: Optional[str]
