"""The drafting graph: a separate compiled LangGraph, no checkpointer.

    resolve_case_and_brief -> collect_structured_case_facts
        -> retrieve_selected_case_documents -> generate_structured_draft
        -> validate_draft

It shares nothing with the case RAG graph or the practice graph beyond the
provider factory. It RETURNS a candidate {body, evidence, missing_facts,
warnings} or an error class; it never writes to the database. The worker
(core/services/drafting/generate.py) decides whether the candidate is stored.

`owner_id` and `case_id` enter the state from the draft row and are only ever
read from there: no node takes an owner, a case or a document id from model
output or from document text. The model's reply is used for the draft body
and nothing else.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from core.models import Case
from core.services.ai_service_factory import get_llm_client
from core.services.drafting import evidence as evidence_service
from core.services.drafting.prompt import build_messages, build_repair_messages
from core.services.drafting.schema import (
    SCHEMA_VERSION,
    SUBTYPES,
    DraftValidationError,
    validate_body,
)

logger = logging.getLogger(__name__)

# Error classes a run can end with.
ERROR_CASE_UNAVAILABLE = "case_unavailable"
ERROR_SOURCE_UNAVAILABLE = "source_unavailable"
ERROR_PROVIDER_UNAVAILABLE = "provider_unavailable"
ERROR_INVALID_OUTPUT = "invalid_output"

MAX_LLM_ATTEMPTS = 2  # the first reply + one repair
MAX_SOURCE_DOCUMENTS = 20
MAX_OUTPUT_TOKENS = {"short": 1500, "standard": 2500, "detailed": 4000}
TONES = ("neutral", "formal", "plain")


class DraftState(TypedDict, total=False):
    # --- Input: set by the worker from the draft row only ---
    owner_id: int
    case_id: int
    subtype: str
    brief: dict

    # --- collected by the server ---
    evidence: list
    facts: list
    excerpts: list
    missing_facts: list
    warnings: list

    # --- generation ---
    raw: str
    body: Any
    validation_errors: list
    llm_calls: int

    # --- result ---
    candidate: Optional[dict]
    error: Optional[str]
    error_class: Optional[str]  # exception class name, for the log line


def _skip_after_error(node):
    def wrapped(state: DraftState) -> dict:
        if state.get("error"):
            return {}
        return node(state)

    wrapped.__name__ = node.__name__
    return wrapped


def _parse(raw: str):
    """The model's reply as a Python value. ValueError when it is not JSON."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("the reply is not valid JSON") from exc


def _check(raw: str, *, subtype: str, allowed: set[str]) -> dict:
    """Parse and validate one reply. Raises DraftValidationError."""
    try:
        body = _parse(raw)
    except ValueError as exc:
        raise DraftValidationError([str(exc)]) from None
    if not isinstance(body, dict):
        raise DraftValidationError(["the reply must be one JSON object"])
    # These two are the server's, whatever the model wrote.
    body["schema_version"] = SCHEMA_VERSION
    body["subtype"] = subtype
    return validate_body(body, allowed_evidence=allowed)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def resolve_case_and_brief(state: DraftState) -> dict:
    owner_id, case_id = state.get("owner_id"), state.get("case_id")
    if not isinstance(owner_id, int) or not isinstance(case_id, int):
        raise ValueError("The drafting graph needs owner_id and case_id from the draft row.")
    if state.get("subtype") not in SUBTYPES:
        raise ValueError("Unknown draft subtype.")
    if not Case.objects.filter(owner_id=owner_id, pk=case_id).exists():
        return {"error": ERROR_CASE_UNAVAILABLE}

    raw_brief = state.get("brief") if isinstance(state.get("brief"), dict) else {}
    source_ids = raw_brief.get("source_document_ids") or []
    if (
        not isinstance(source_ids, list)
        or len(source_ids) > MAX_SOURCE_DOCUMENTS
        or not all(isinstance(i, int) and not isinstance(i, bool) for i in source_ids)
    ):
        return {"error": ERROR_SOURCE_UNAVAILABLE}
    length = raw_brief.get("length")
    tone = raw_brief.get("tone")
    return {
        "brief": {
            "instructions": str(raw_brief.get("instructions") or "")[:2000],
            "audience": str(raw_brief.get("audience") or "")[:200],
            "tone": tone if tone in TONES else "neutral",
            "length": length if length in MAX_OUTPUT_TOKENS else "standard",
            "source_document_ids": source_ids,
        },
        "llm_calls": 0,
    }


def collect_structured_case_facts(state: DraftState) -> dict:
    collected = evidence_service.collect_case_evidence(
        owner=state["owner_id"], case_id=state["case_id"]
    )
    if collected is None:
        return {"error": ERROR_CASE_UNAVAILABLE}
    return {
        "evidence": collected["evidence"],
        "facts": collected["facts"],
        "missing_facts": collected["missing_facts"],
        "warnings": collected["warnings"],
    }


def retrieve_selected_case_documents(state: DraftState) -> dict:
    source_ids = state["brief"]["source_document_ids"]
    if not source_ids:
        return {"excerpts": []}
    try:
        found = evidence_service.collect_document_evidence(
            owner=state["owner_id"],
            case_id=state["case_id"],
            document_ids=source_ids,
            instructions=state["brief"]["instructions"],
        )
    except evidence_service.SourceUnavailable:
        return {"error": ERROR_SOURCE_UNAVAILABLE}
    return {
        "evidence": state["evidence"] + found["evidence"],
        "excerpts": found["excerpts"],
        "warnings": state["warnings"] + found["warnings"],
    }


def generate_structured_draft(state: DraftState) -> dict:
    """The first reply and, when it does not validate, one repair attempt."""
    subtype = state["subtype"]
    allowed = {entry["id"] for entry in state["evidence"]}
    messages = build_messages(
        subtype=subtype, brief=state["brief"], facts=state["facts"], excerpts=state["excerpts"]
    )
    max_tokens = MAX_OUTPUT_TOKENS[state["brief"]["length"]]
    errors: list[str] = []
    calls = 0
    raw = ""
    try:
        client = get_llm_client()
        for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
            # Bounded by the client's own timeout and retry settings
            # (LLM_REQUEST_TIMEOUT_SECONDS / LLM_MAX_RETRIES) and max_tokens.
            raw = client.generate_with_json(messages, temperature=0.2, max_tokens=max_tokens)
            calls = attempt
            try:
                body = _check(raw, subtype=subtype, allowed=allowed)
            except DraftValidationError as exc:
                errors = exc.errors
                messages = build_repair_messages(messages, raw, errors)
                continue
            return {"raw": raw, "body": body, "validation_errors": [], "llm_calls": calls}
    except Exception as exc:  # noqa: BLE001 -- provider/network/configuration failures
        return {
            "error": ERROR_PROVIDER_UNAVAILABLE,
            "error_class": type(exc).__name__,
            "llm_calls": calls,
        }
    return {"raw": raw, "body": None, "validation_errors": errors, "llm_calls": calls}


def validate_draft(state: DraftState) -> dict:
    """The gate. The body is validated again here, against the collected
    evidence, before it can become a candidate."""
    if state.get("body") is None:
        return {"error": ERROR_INVALID_OUTPUT, "error_class": "DraftValidationError"}
    allowed = {entry["id"] for entry in state["evidence"]}
    try:
        body = validate_body(state["body"], allowed_evidence=allowed)
    except DraftValidationError:
        return {"error": ERROR_INVALID_OUTPUT, "error_class": "DraftValidationError"}
    return {
        "candidate": {
            "body": body,
            "evidence": state["evidence"],
            "missing_facts": state["missing_facts"],
            "warnings": state["warnings"],
        }
    }


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

_NODES = (
    resolve_case_and_brief,
    collect_structured_case_facts,
    retrieve_selected_case_documents,
    generate_structured_draft,
    validate_draft,
)


def build_draft_graph():
    workflow = StateGraph(DraftState)
    workflow.add_node(_NODES[0].__name__, _NODES[0])
    for node in _NODES[1:]:
        workflow.add_node(node.__name__, _skip_after_error(node))
    workflow.set_entry_point(_NODES[0].__name__)
    for before, after in zip(_NODES, _NODES[1:]):
        workflow.add_edge(before.__name__, after.__name__)
    workflow.add_edge(_NODES[-1].__name__, END)
    return workflow.compile()


_graph = None


def get_draft_graph():
    global _graph
    if _graph is None:
        _graph = build_draft_graph()
    return _graph


def run_draft_graph(*, owner_id: int, case_id: int, subtype: str, brief: dict) -> DraftState:
    """Run one generation. Every argument comes from the draft row. Returns
    the final state: `candidate` is set on success, `error` otherwise."""
    return get_draft_graph().invoke(
        {"owner_id": owner_id, "case_id": case_id, "subtype": subtype, "brief": brief}
    )
