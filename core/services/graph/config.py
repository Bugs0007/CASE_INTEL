"""
Configuration constants for the Case Intel LangGraph pipeline.

Changes from original:
  - Added SEARCH_TOP_K  (was read from settings.AI_SEARCH_TOP_K inline).
  - Added MAX_CONVERSATION_HISTORY.
  - Removed CLARIFICATION_THRESHOLD (query_router gone).
  - Query type constants kept identical so existing DB values stay valid.
"""

# ---------------------------------------------------------------------------
# Query types — stored in AgentState["query_type"]
# ---------------------------------------------------------------------------
QUERY_TYPE_SIMPLE_QA  = "simple_qa"
QUERY_TYPE_SUMMARIZE  = "summarize"
QUERY_TYPE_COMPARE    = "compare"
QUERY_TYPE_TIMELINE   = "timeline"

# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

# How many final results to return from VectorSearchService.search().
# The service internally fetches SEARCH_TOP_K * 3 candidates before
# RRF fusion and cross-encoder reranking narrow them down.
SEARCH_TOP_K = 6

# Rerank score below which the answer is prefixed with a low-confidence disclaimer.
# Cross-encoder scores are roughly in [-10, 10]; after normalisation by the
# service they land in [0, 1].  0.35 is a reasonable "uncertain" threshold.
CONFIDENCE_THRESHOLD = 0.35

# ---------------------------------------------------------------------------
# LLM generation
# ---------------------------------------------------------------------------
LLM_TEMPERATURE  = 0.1    # low temperature for factual legal answers
LLM_MAX_TOKENS   = 1024

# How many prior conversation turns to include as context in the answer prompt
MAX_CONVERSATION_HISTORY = 4
