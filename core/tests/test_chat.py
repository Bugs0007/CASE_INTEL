"""API-level tests for the Case Bot chat endpoint (``POST /api/chat/``).

The focus here is the *failure* path. When the LangGraph pipeline throws
(embedding or LLM provider down), ``AIWorkflowService.process_query`` swaps in
a graceful fallback answer -- and the endpoint must return that with HTTP 200,
not turn it into a 4xx. It used to 400 with
``{"query_type": ["This field may not be blank."]}`` because the response was
run back through a strict serializer before being sent.

Only the compiled LangGraph is mocked: ``_ai_service._graph`` is set to a
stand-in so ``_get_graph()`` never builds the real graph and no LLM or
embedding client is constructed. ``patch.object`` restores the original
(``None``) after each test, so order does not matter.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.services.vector_search_service import VectorSearchService
from core.views import chat as chat_view

# Substring of the canned message ai_workflow.process_query returns when the
# graph raises -- see its top-level ``except`` handler.
FALLBACK_ANSWER_MARKER = "error while processing"

RESPONSE_KEYS = {
    "answer",
    "confidence",
    "query_type",
    "requires_clarification",
    "clarification_question",
    "message_id",
    "conversation_id",
    "citations",
}


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="chat-advocate", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


def _stub_graph(*, result=None, exc=None):
    """Patch the workflow singleton's compiled graph with a stand-in.

    A non-None ``_graph`` makes ``AIWorkflowService._get_graph()`` skip
    ``build_legal_ai_graph()``, so the real graph (and its LLM/embedding
    clients) is never constructed.
    """
    graph = MagicMock()
    if exc is not None:
        graph.invoke.side_effect = exc
    else:
        graph.invoke.return_value = result
    return patch.object(chat_view._ai_service, "_graph", graph)


@pytest.mark.django_db
def test_graph_failure_returns_200_with_graceful_fallback(api):
    with _stub_graph(exc=RuntimeError("embedding provider unreachable")):
        resp = api.post(
            "/api/chat/",
            {"query": "What was the settlement amount?"},
            format="json",
        )

    assert resp.status_code == 200  # regression: was 400 {"query_type": [...]}
    body = resp.data
    assert FALLBACK_ANSWER_MARKER in body["answer"].lower()
    assert body["confidence"] == 0.0
    assert body["citations"] == []
    assert body["requires_clarification"] is False
    assert body["clarification_question"] is None
    assert isinstance(body["message_id"], int)  # assistant message still persisted
    assert set(body) == RESPONSE_KEYS


@pytest.mark.django_db
def test_successful_query_returns_200_with_answer_and_ids(api):
    graph_state = {
        "answer": "The settlement amount was Rs 5,00,000.",
        "answer_confidence": 0.82,
        "citations": [],
        "query_type": "simple_qa",
        "requires_clarification": False,
        "clarification_question": None,
        "error": None,
    }
    with _stub_graph(result=graph_state):
        resp = api.post("/api/chat/", {"query": "settlement amount?"}, format="json")

    assert resp.status_code == 200
    body = resp.data
    assert body["answer"] == graph_state["answer"]
    assert body["confidence"] == 0.82
    assert body["query_type"] == "simple_qa"
    assert body["citations"] == []
    assert isinstance(body["message_id"], int)
    assert isinstance(body["conversation_id"], int)


def test_search_falls_back_to_keyword_only_when_embedding_provider_fails():
    embedding = MagicMock()
    embedding.embed_text.side_effect = ConnectionError("embedding provider unreachable")
    service = VectorSearchService(embedding_service=embedding, use_reranker=False)

    keyword_chunk = MagicMock()
    keyword_chunk.id = 101

    with patch.object(service, "_keyword_search", return_value=[keyword_chunk]) as keyword_search:
        with patch.object(service, "_vector_search") as vector_search:
            results = service.search(
                "what was the penalty clause?", owner_id=42, case_id=7, top_k=5
            )

    vector_search.assert_not_called()  # bailed out before the pgvector query
    keyword_search.assert_called_once()
    assert [result.chunk for result in results] == [keyword_chunk]
