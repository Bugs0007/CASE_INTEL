"""Regression tests for LangGraph node functions in core/services/graph/nodes.py.

core/tests/test_chat.py's test_graph_failure_returns_200_with_graceful_fallback
mocks the *entire compiled graph* (`_ai_service._graph`), so it never actually
calls generate_answer() or an LLM client -- it only proves the response shape
is right once *something, somewhere* raises. That's exactly why a retired/
invalid GROQ_MODEL (a real provider failure, not a wiring bug) shipped
uncaught: nothing in the suite ever exercised generate_answer()'s own LLM
call against a realistic failure.

These tests call generate_answer() directly with a mock LLM client that
raises the same exception shape Groq returns for a retired model (a 404
openai.NotFoundError), and assert it degrades to the raw-excerpts fallback
instead of propagating -- which is what keeps the failure from ever reaching
ai_workflow.py's generic top-level "I encountered an error" handler.
"""

from unittest.mock import MagicMock

import httpx
import pytest
from openai import NotFoundError

from core.services.graph.nodes import generate_answer


def _groq_model_not_found_error() -> NotFoundError:
    """Build the same exception shape LLMClient.generate() raises when
    GROQ_MODEL names a model Groq has retired -- a real 404 response body,
    not a generic RuntimeError stand-in."""
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(
        status_code=404,
        request=request,
        json={
            "error": {
                "message": (
                    "The model `llama-3.3-70b-versatile` does not exist or "
                    "you do not have access to it."
                ),
                "type": "invalid_request_error",
                "code": "model_not_found",
            }
        },
    )
    return NotFoundError(
        message="model_not_found",
        response=response,
        body={"code": "model_not_found"},
    )


def _make_state(**overrides) -> dict:
    base = {
        "user_query": "What was the settlement amount?",
        "owner_id": 1,
        "case_id": 7,
        "conversation_id": 3,
        "conversation_history": [],
        "tracking_context": None,
        "hyde_passage": "The parties agreed to a settlement.",
        "query_type": "simple_qa",
        "requires_clarification": False,
        "clarification_question": None,
        "retrieved_chunks": [
            {
                "chunk_id": 101,
                "document_id": 55,
                "chunk_index": 0,
                "text": "The settlement amount was Rs 5,00,000, payable within 30 days.",
                "score": 0.82,
                "metadata": {"filename": "settlement_deed.pdf", "document_type": "agreement"},
            },
        ],
        "chunk_count": 1,
        "search_confidence": 0.82,
        "answer": "",
        "answer_confidence": 0.0,
        "citations": [],
        "error": None,
    }
    base.update(overrides)
    return base


def test_generate_answer_falls_back_when_llm_call_fails():
    """The core Fix 1 regression: a real provider 404 (retired model) must
    not propagate out of generate_answer() -- it should degrade to the raw
    retrieved excerpts instead."""
    llm = MagicMock()
    llm.generate.side_effect = _groq_model_not_found_error()

    state = _make_state()
    result = generate_answer(state, llm=llm)

    assert result["answer"] != ""
    assert "settlement_deed.pdf" in result["answer"]
    assert "Rs 5,00,000" in result["answer"]
    assert result["answer_confidence"] == 0.0
    assert result["requires_clarification"] is False
    assert result["clarification_question"] is None
    # One citation per retrieved chunk, sourced directly (no [Doc N] to
    # regex-match since the LLM never produced output).
    assert result["citations"] == [
        {
            "chunk_id": 101,
            "document_id": 55,
            "citation_text": "The settlement amount was Rs 5,00,000, payable within 30 days.",
            "source_type": "chunk",
        }
    ]


def test_generate_answer_fallback_includes_tracking_block_when_present():
    """Tracking-only queries (no chunks) must still degrade gracefully, not
    just the chunks case."""
    llm = MagicMock()
    llm.generate.side_effect = _groq_model_not_found_error()

    state = _make_state(
        retrieved_chunks=[],
        chunk_count=0,
        search_confidence=0.0,
        tracking_context={
            "block": "Next hearing: 2026-10-01. Stage: Arguments.",
            "source_label": "eCourts tracking data (refreshed 16 Sep 2026)",
        },
    )
    result = generate_answer(state, llm=llm)

    assert "Next hearing: 2026-10-01" in result["answer"]
    assert result["answer_confidence"] == 0.0
    assert result["citations"] == []


def test_generate_answer_succeeds_normally_when_llm_call_works():
    """Sanity check that the try/except doesn't change the happy path."""
    llm = MagicMock()
    llm.generate.return_value = "The settlement amount was Rs 5,00,000 [Doc 1]."

    state = _make_state()
    result = generate_answer(state, llm=llm)

    assert "Rs 5,00,000" in result["answer"]
    assert result["citations"][0]["chunk_id"] == 101
    assert result["answer_confidence"] > 0.0
