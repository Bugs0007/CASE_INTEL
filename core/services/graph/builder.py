"""
LangGraph graph builder for the Case Intel AI workflow.

Constructs the complete state graph by wiring nodes and conditional
edges together. The compiled graph is a callable that transforms
AgentState from initial input to final response.
"""

import logging
from functools import partial

from langgraph.graph import END, StateGraph

from core.services.graph import config
from core.services.graph.nodes import (
    answer_generator,
    chunk_ranker,
    citation_extractor,
    handle_low_confidence,
    handle_no_results,
    query_analyzer,
    query_router,
    response_formatter,
    vector_search,
)
from core.services.graph.state import AgentState
from core.services.llm_client import LLMClient
from core.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def _should_clarify(state: AgentState) -> str:
    """Route after query_router: clarify or proceed to analysis."""
    if state.get("requires_clarification"):
        return "clarify"
    return "analyze"


def _check_results(state: AgentState) -> str:
    """Route after vector_search based on result quality."""
    if state["chunk_count"] == 0:
        return "no_results"
    if state["search_confidence"] < config.CONFIDENCE_THRESHOLD:
        return "low_confidence"
    return "rank"


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------

def build_legal_ai_graph(
    llm: LLMClient,
    search_service: VectorSearchService,
) -> StateGraph:
    """Build and compile the LangGraph workflow.

    Uses functools.partial to inject service dependencies into node
    functions, keeping the nodes themselves stateless and testable.

    Args:
        llm: The LLM client for chat completions.
        search_service: The vector search service for pgvector queries.

    Returns:
        A compiled LangGraph StateGraph ready for invocation.

    Flow diagram:
        route_query
            ├── (clarify) → END
            └── (analyze) → analyze_query → vector_search
                                                ├── (no_results)      → handle_no_results → END
                                                ├── (low_confidence)  → handle_low_confidence → extract_citations → format_response → END
                                                └── (rank)            → rank_chunks → generate_answer → extract_citations → format_response → END
    """
    workflow = StateGraph(AgentState)

    # --- Register nodes with injected dependencies ---
    workflow.add_node("route_query", partial(query_router, llm=llm))
    workflow.add_node("analyze_query", partial(query_analyzer, llm=llm))
    workflow.add_node(
        "vector_search", partial(vector_search, search_service=search_service)
    )
    workflow.add_node("rank_chunks", partial(chunk_ranker, llm=llm))
    workflow.add_node("generate_answer", partial(answer_generator, llm=llm))
    workflow.add_node("extract_citations", partial(citation_extractor, llm=llm))
    workflow.add_node("format_response", response_formatter)
    workflow.add_node("handle_no_results", handle_no_results)
    workflow.add_node("handle_low_confidence", partial(handle_low_confidence, llm=llm))

    # --- Entry point ---
    workflow.set_entry_point("route_query")

    # --- Edges ---
    workflow.add_conditional_edges(
        "route_query",
        _should_clarify,
        {
            "clarify": END,
            "analyze": "analyze_query",
        },
    )

    workflow.add_edge("analyze_query", "vector_search")

    workflow.add_conditional_edges(
        "vector_search",
        _check_results,
        {
            "no_results": "handle_no_results",
            "low_confidence": "handle_low_confidence",
            "rank": "rank_chunks",
        },
    )

    # Normal flow
    workflow.add_edge("rank_chunks", "generate_answer")
    workflow.add_edge("generate_answer", "extract_citations")
    workflow.add_edge("extract_citations", "format_response")
    workflow.add_edge("format_response", END)

    # No results terminates
    workflow.add_edge("handle_no_results", END)

    # Low confidence still gets citations
    workflow.add_edge("handle_low_confidence", "extract_citations")

    compiled = workflow.compile()
    logger.info("Legal AI graph compiled successfully.")
    return compiled
