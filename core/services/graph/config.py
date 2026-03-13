"""
Configuration constants for the LangGraph AI workflow.

All tunable parameters are centralized here. Values are read from
Django settings (which sources them from environment variables)
with sensible defaults.
"""

from django.conf import settings


# Search parameters
SEARCH_TOP_K: int = getattr(settings, "AI_SEARCH_TOP_K", 10)
RERANK_TOP_K: int = getattr(settings, "AI_RERANK_TOP_K", 5)
CONFIDENCE_THRESHOLD: float = getattr(settings, "AI_CONFIDENCE_THRESHOLD", 0.5)
MAX_CONVERSATION_HISTORY: int = getattr(settings, "AI_MAX_CONVERSATION_HISTORY", 5)

# Chunk deduplication: max chunks allowed from a single document
MAX_CHUNKS_PER_DOCUMENT: int = 2

# LLM generation parameters
LLM_TEMPERATURE: float = 0.1
LLM_MAX_TOKENS: int = 4096

# Query types
QUERY_TYPE_SIMPLE_QA = "simple_qa"
QUERY_TYPE_SUMMARIZE = "summarize"
QUERY_TYPE_COMPARE = "compare"
QUERY_TYPE_TIMELINE = "timeline"
QUERY_TYPE_UNCLEAR = "unclear"

VALID_QUERY_TYPES = {
    QUERY_TYPE_SIMPLE_QA,
    QUERY_TYPE_SUMMARIZE,
    QUERY_TYPE_COMPARE,
    QUERY_TYPE_TIMELINE,
    QUERY_TYPE_UNCLEAR,
}
