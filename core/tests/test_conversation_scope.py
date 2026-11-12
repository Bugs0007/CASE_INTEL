"""Conversation scope (case / legacy_documents / practice) and Message.references.

Covers the 0051 backfill for each legacy row shape, the check constraint,
scope derivation for callers that predate scopes, the old chat endpoint
refusing a practice conversation, the conversation list's scope filter, and
cross-owner isolation of a practice conversation.

Only the compiled LangGraph is mocked (same stand-in as test_chat.py), so no
LLM or embedding client is ever constructed.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APIClient

from core.models import Case, Conversation, Message
from core.views import chat as chat_view

BEFORE = [("core", "0050_case_business_entry")]
AFTER = [("core", "0051_conversation_scope_message_references")]

GRAPH_STATE = {
    "answer": "An answer.",
    "answer_confidence": 0.8,
    "citations": [],
    "query_type": "simple_qa",
    "requires_clarification": False,
    "clarification_question": None,
    "error": None,
}


def _stub_graph():
    graph = MagicMock()
    graph.invoke.return_value = GRAPH_STATE
    return patch.object(chat_view._ai_service, "_graph", graph)


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _rows(resp):
    data = resp.data
    return data["results"] if isinstance(data, dict) else data


def _ids(resp):
    return {row["id"] for row in _rows(resp)}


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username="scope-a", password="pw-12345")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="scope-b", password="pw-12345")


@pytest.fixture
def case_a(user_a):
    return Case.objects.create(
        owner=user_a, case_number="S-001", title="Scope Case", client_name="Client"
    )


@pytest.fixture
def conversations(user_a, case_a):
    """One conversation of each scope, all owned by user_a."""
    return {
        "case": Conversation.objects.create(owner=user_a, case=case_a, title="case"),
        "legacy": Conversation.objects.create(owner=user_a, title="legacy"),
        "practice": Conversation.objects.create(
            owner=user_a, scope=Conversation.SCOPE_PRACTICE, title="practice"
        ),
    }


# ---------------------------------------------------------------------------
# Migration backfill
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_migration_backfills_scope_and_preserves_rows():
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(BEFORE)
        old_apps = executor.loader.project_state(BEFORE).apps
        OldUser = old_apps.get_model("auth", "User")
        OldCase = old_apps.get_model("core", "Case")
        OldConversation = old_apps.get_model("core", "Conversation")
        OldMessage = old_apps.get_model("core", "Message")
        OldCitation = old_apps.get_model("core", "Citation")

        owner = OldUser.objects.create(username="backfill-owner")
        case = OldCase.objects.create(
            owner=owner, case_number="M-001", title="Old Case", client_name="C"
        )
        with_case = OldConversation.objects.create(
            owner=owner, case=case, title="About the case"
        )
        without_case = OldConversation.objects.create(
            owner=owner, case=None, title="All documents"
        )
        untitled = OldConversation.objects.create(owner=owner, case=None, title=None)
        message = OldMessage.objects.create(
            owner=owner, conversation=with_case, role="assistant", content="kept"
        )
        citation = OldCitation.objects.create(
            owner=owner, message=message, source_type="chunk", citation_text="cited"
        )

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        new_apps = executor.loader.project_state(AFTER).apps
        NewConversation = new_apps.get_model("core", "Conversation")
        NewMessage = new_apps.get_model("core", "Message")
        NewCitation = new_apps.get_model("core", "Citation")

        rows = {c.pk: c for c in NewConversation.objects.all()}
        assert set(rows) == {with_case.pk, without_case.pk, untitled.pk}
        assert rows[with_case.pk].scope == "case"
        assert rows[with_case.pk].case_id == case.pk
        assert rows[with_case.pk].title == "About the case"
        assert rows[without_case.pk].scope == "legacy_documents"
        assert rows[without_case.pk].title == "All documents"
        assert rows[untitled.pk].scope == "legacy_documents"
        assert rows[untitled.pk].title is None

        kept = NewMessage.objects.get(pk=message.pk)
        assert kept.conversation_id == with_case.pk
        assert kept.content == "kept"
        assert kept.references == []
        assert NewCitation.objects.get(pk=citation.pk).message_id == message.pk
    finally:
        # Leave the schema at head whatever happened above.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


# ---------------------------------------------------------------------------
# Model: derived scope + check constraint
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_scope_is_derived_from_case_when_not_given(conversations):
    assert conversations["case"].scope == "case"
    assert conversations["legacy"].scope == "legacy_documents"
    assert conversations["practice"].scope == "practice"
    conversations["case"].refresh_from_db()
    assert conversations["case"].scope == "case"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "scope, with_case",
    [
        ("case", False),
        ("legacy_documents", True),
        ("practice", True),
        ("", False),
        ("", True),
        ("something_else", False),
    ],
)
def test_check_constraint_rejects_scope_case_mismatch(user_a, case_a, scope, with_case):
    # bulk_create skips save(), so nothing derives or repairs the scope.
    row = Conversation(owner=user_a, case=case_a if with_case else None, scope=scope)
    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.bulk_create([row])


@pytest.mark.django_db
def test_message_references_default_and_round_trip(user_a, conversations):
    convo = conversations["practice"]
    plain = Message.objects.create(
        owner=user_a, conversation=convo, role="user", content="q"
    )
    assert plain.references == []

    ref = {
        "kind": "hearing",
        "id": 7,
        "case_id": 3,
        "label": "Hearing on 12 Nov",
        "recorded_at": "2026-11-12",
    }
    answer = Message.objects.create(
        owner=user_a,
        conversation=convo,
        role="assistant",
        content="a",
        references=[ref],
    )
    answer.refresh_from_db()
    assert answer.references == [ref]

    resp = _client(user_a).get(f"/api/conversations/{convo.id}/messages/")
    assert resp.status_code == 200
    assert [row["references"] for row in _rows(resp)] == [[], [ref]]


# ---------------------------------------------------------------------------
# POST /api/chat/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_chat_creates_case_and_legacy_scopes(user_a, case_a):
    api = _client(user_a)
    with _stub_graph():
        with_case = api.post(
            "/api/chat/", {"query": "q", "case_id": case_a.id}, format="json"
        )
        without_case = api.post("/api/chat/", {"query": "q"}, format="json")

    assert with_case.status_code == 200
    assert without_case.status_code == 200
    assert Conversation.objects.get(id=with_case.data["conversation_id"]).scope == "case"
    assert (
        Conversation.objects.get(id=without_case.data["conversation_id"]).scope
        == "legacy_documents"
    )


@pytest.mark.django_db
def test_chat_rejects_practice_conversation_like_a_missing_one(user_a, conversations):
    api = _client(user_a)
    practice = conversations["practice"]
    missing_id = practice.id + 10_000

    with _stub_graph() as graph:
        practice_resp = api.post(
            "/api/chat/", {"query": "q", "conversation_id": practice.id}, format="json"
        )
        missing_resp = api.post(
            "/api/chat/", {"query": "q", "conversation_id": missing_id}, format="json"
        )
        graph.invoke.assert_not_called()

    assert practice_resp.status_code == missing_resp.status_code == 404
    assert practice_resp.data == {
        "detail": f"Conversation with id {practice.id} does not exist."
    }
    assert missing_resp.data == {
        "detail": f"Conversation with id {missing_id} does not exist."
    }
    assert not Message.objects.filter(conversation=practice).exists()


@pytest.mark.django_db
def test_chat_still_continues_case_and_legacy_conversations(user_a, conversations):
    api = _client(user_a)
    with _stub_graph():
        for key in ("case", "legacy"):
            convo = conversations[key]
            resp = api.post(
                "/api/chat/", {"query": "q", "conversation_id": convo.id}, format="json"
            )
            assert resp.status_code == 200
            assert resp.data["conversation_id"] == convo.id


# ---------------------------------------------------------------------------
# GET /api/conversations/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_excludes_practice_by_default(user_a, conversations):
    resp = _client(user_a).get("/api/conversations/")
    assert resp.status_code == 200
    assert _ids(resp) == {conversations["case"].id, conversations["legacy"].id}


@pytest.mark.django_db
def test_list_by_case_id_is_unchanged(user_a, case_a, conversations):
    resp = _client(user_a).get(f"/api/conversations/?case_id={case_a.id}")
    assert resp.status_code == 200
    assert _ids(resp) == {conversations["case"].id}


@pytest.mark.django_db
def test_list_scope_practice_returns_only_practice(user_a, case_a, conversations):
    api = _client(user_a)
    resp = api.get("/api/conversations/?scope=practice")
    assert resp.status_code == 200
    assert _ids(resp) == {conversations["practice"].id}
    assert _rows(resp)[0]["scope"] == "practice"

    # A practice conversation never has a case, so the two filters together
    # match nothing.
    both = api.get(f"/api/conversations/?scope=practice&case_id={case_a.id}")
    assert _ids(both) == set()


@pytest.mark.django_db
def test_detail_export_and_delete_work_for_a_practice_conversation(
    user_a, conversations
):
    api = _client(user_a)
    practice = conversations["practice"]
    Message.objects.create(
        owner=user_a, conversation=practice, role="user", content="What is due?"
    )

    detail = api.get(f"/api/conversations/{practice.id}/")
    assert detail.status_code == 200
    assert detail.data["scope"] == "practice"
    assert detail.data["messages"][0]["references"] == []

    assert api.get(f"/api/conversations/{practice.id}/export/").status_code == 200
    assert api.delete(f"/api/conversations/{practice.id}/").status_code == 204
    assert not Conversation.objects.filter(id=practice.id).exists()


# ---------------------------------------------------------------------------
# Cross-owner isolation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_practice_conversation_is_invisible_to_another_owner(
    user_a, user_b, conversations
):
    practice = conversations["practice"]
    Message.objects.create(
        owner=user_a,
        conversation=practice,
        role="assistant",
        content="private",
        references=[
            {"kind": "case", "id": 1, "case_id": 1, "label": "x", "recorded_at": None}
        ],
    )
    api_b = _client(user_b)

    assert _ids(api_b.get("/api/conversations/?scope=practice")) == set()
    assert _ids(api_b.get("/api/conversations/")) == set()
    assert api_b.get(f"/api/conversations/{practice.id}/").status_code == 404
    assert api_b.get(f"/api/conversations/{practice.id}/export/").status_code == 404
    assert api_b.delete(f"/api/conversations/{practice.id}/").status_code == 404

    messages = api_b.get(f"/api/conversations/{practice.id}/messages/")
    assert messages.status_code == 200
    assert _rows(messages) == []

    with _stub_graph():
        chat = api_b.post(
            "/api/chat/", {"query": "q", "conversation_id": practice.id}, format="json"
        )
    assert chat.status_code == 404
    assert Conversation.objects.filter(id=practice.id).exists()


@pytest.mark.django_db
def test_list_carries_case_title_for_the_case_bot_sidebar(user_a, case_a, conversations):
    rows = {r["id"]: r for r in _rows(_client(user_a).get("/api/conversations/"))}
    assert rows[conversations["case"].id]["case_title"] == case_a.title
    practice = _rows(_client(user_a).get("/api/conversations/?scope=practice"))[0]
    assert practice["case_title"] is None
