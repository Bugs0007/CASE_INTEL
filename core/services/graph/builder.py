"""
LangGraph graph builder for the Case Intel AI workflow.

Simplified from the original 9-node graph to a lean 3-node pipeline:

    hyde_expand  →  hybrid_search  →  generate_answer  →  END

LLM calls per query:  2  (was 6)
Estimated latency:    8-12 sec  (was 30-60 sec)
"""

import logging
from functools import partial

from langgraph.graph import END, StateGraph

from core.services.graph.nodes import (
    generate_answer,
    hybrid_search,
    hyde_expand,
)
from core.services.graph.state import AgentState
from core.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)


def build_legal_ai_graph(
    llm,
    search_service: VectorSearchService,
) -> StateGraph:
    """Build and compile the lean 3-node LangGraph workflow.

    Args:
        llm: OllamaLLMClient (or any LLMClient-compatible object).
        search_service: VectorSearchService with hybrid search enabled.

    Returns:
        Compiled LangGraph StateGraph ready for invocation.

    Flow:
        hyde_expand → hybrid_search → generate_answer → END
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("hyde_expand", partial(hyde_expand, llm=llm))
    workflow.add_node(
        "hybrid_search", partial(hybrid_search, search_service=search_service)
    )
    workflow.add_node("generate_answer", partial(generate_answer, llm=llm))

    workflow.set_entry_point("hyde_expand")
    workflow.add_edge("hyde_expand", "hybrid_search")
    workflow.add_edge("hybrid_search", "generate_answer")
    workflow.add_edge("generate_answer", END)

    compiled = workflow.compile()
    logger.info("Lean 3-node legal AI graph compiled successfully.")
    return compiled
