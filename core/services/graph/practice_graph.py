"""The practice-assistant graph: a separate compiled LangGraph.

    validate_scope -> select_intent -> run_read -> present -> validate_references

It shares nothing with the case RAG graph (builder.py / nodes.py / state.py)
beyond the provider factory: no retrieval, no embeddings, no document chunks.
A turn is answered from the practice read model (practice_assistant/reads.py)
and makes at most one bounded model call (see practice_nodes.py).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from core.services.graph import practice_nodes
from core.services.practice_assistant.contracts import SCOPE_PERSONAL


class PracticeState(TypedDict, total=False):
    # --- Input: set by the server from the authenticated request only ---
    owner: Any  # the requesting User; every read filters by it
    scope: str
    query: str
    selected_day: Optional[date]
    case_id: Optional[int]  # already verified as the owner's by the view
    now: datetime  # aware India time; the turn's as_of

    # --- select_intent ---
    intent: Optional[str]
    args: dict
    routed_by: str  # rule | llm | none
    llm_calls: int

    # --- run_read / present / validate_references ---
    status: str
    answer: str
    summary: Optional[dict]
    sources: list
    case_candidates: list
    action_card: Optional[dict]


def build_practice_graph():
    workflow = StateGraph(PracticeState)
    workflow.add_node("validate_scope", practice_nodes.validate_scope)
    workflow.add_node("select_intent", practice_nodes.select_intent)
    workflow.add_node("run_read", practice_nodes.run_read)
    workflow.add_node("present", practice_nodes.present)
    workflow.add_node("validate_references", practice_nodes.validate_references)

    workflow.set_entry_point("validate_scope")
    workflow.add_edge("validate_scope", "select_intent")
    workflow.add_edge("select_intent", "run_read")
    workflow.add_edge("run_read", "present")
    workflow.add_edge("present", "validate_references")
    workflow.add_edge("validate_references", END)
    return workflow.compile()


_graph = None


def get_practice_graph():
    global _graph
    if _graph is None:
        _graph = build_practice_graph()
    return _graph


def run_practice_turn(
    *,
    owner,
    query: str,
    now: datetime,
    selected_day: Optional[date] = None,
    case_id: Optional[int] = None,
) -> PracticeState:
    """Run one turn. `owner` is the authenticated user and `case_id`, when
    given, must already be verified as theirs. Returns the final state."""
    return get_practice_graph().invoke(
        {
            "owner": owner,
            "scope": SCOPE_PERSONAL,
            "query": query,
            "selected_day": selected_day,
            "case_id": case_id,
            "now": now,
        }
    )
