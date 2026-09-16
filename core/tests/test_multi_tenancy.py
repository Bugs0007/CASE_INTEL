"""Row-level multi-tenancy isolation tests.

Two independent advocates (user_a/user_b), each with their own Case. For
every endpoint that touches Case (or something hanging off it), user A must
never be able to list, retrieve, update, or delete anything owned by user B.
"""

from contextlib import ExitStack, contextmanager
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import (
    Case,
    Citation,
    ClientContact,
    Document,
    DocumentChunk,
    Hearing,
    InviteToken,
)
from core.services.vector_search_service import VectorSearchService
from core.views import chat as chat_view


@pytest.fixture
def user_a():
    return User.objects.create_user(username="alice", password="alice-pass-123")


@pytest.fixture
def user_b():
    return User.objects.create_user(username="bob", password="bob-pass-123")


def _authed_client(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def client_a(user_a):
    return _authed_client(user_a)


@pytest.fixture
def client_b(user_b):
    return _authed_client(user_b)


@pytest.fixture
def case_a(user_a):
    return Case.objects.create(
        owner=user_a, case_number="A-001", title="Alice's Case", client_name="Alice Client"
    )


@pytest.fixture
def case_b(user_b):
    return Case.objects.create(
        owner=user_b, case_number="B-001", title="Bob's Case", client_name="Bob Client"
    )


@pytest.mark.django_db
class TestCaseIsolation:
    def test_list_excludes_other_users_case(self, client_a, case_a, case_b):
        resp = client_a.get("/api/cases/")
        assert resp.status_code == 200
        ids = {c["id"] for c in resp.data}
        assert case_a.id in ids
        assert case_b.id not in ids

    def test_retrieve_other_users_case_404s(self, client_a, case_b):
        resp = client_a.get(f"/api/cases/{case_b.id}/")
        assert resp.status_code == 404

    def test_update_other_users_case_404s(self, client_a, case_b):
        resp = client_a.patch(
            f"/api/cases/{case_b.id}/", {"title": "Hacked"}, format="json"
        )
        assert resp.status_code == 404
        case_b.refresh_from_db()
        assert case_b.title == "Bob's Case"

    def test_delete_other_users_case_404s(self, client_a, case_b):
        resp = client_a.delete(f"/api/cases/{case_b.id}/")
        assert resp.status_code == 404
        assert Case.objects.filter(id=case_b.id).exists()

    def test_own_case_retrieve_update_delete_still_work(self, client_a, case_a):
        resp = client_a.get(f"/api/cases/{case_a.id}/")
        assert resp.status_code == 200

        resp = client_a.patch(
            f"/api/cases/{case_a.id}/", {"title": "Updated"}, format="json"
        )
        assert resp.status_code == 200
        case_a.refresh_from_db()
        assert case_a.title == "Updated"

        resp = client_a.delete(f"/api/cases/{case_a.id}/")
        assert resp.status_code == 204
        assert not Case.objects.filter(id=case_a.id).exists()

    def test_create_ignores_client_supplied_owner(self, client_a, user_b):
        resp = client_a.post(
            "/api/cases/",
            {"case_number": "A-002", "title": "Manually Entered Case", "owner": user_b.id},
            format="json",
        )
        assert resp.status_code == 201
        case = Case.objects.get(case_number="A-002")
        # owner is stamped from request.user (OwnerScopedMixin.perform_create),
        # never from client-supplied input -- the "owner": user_b.id above
        # must be silently ignored.
        assert case.owner_id != user_b.id

    def test_create_same_case_number_across_users_succeeds(self, client_b, case_a):
        # case_number is unique per owner, not globally -- a real case is
        # routinely tracked by more than one advocate (co-counsel,
        # opposing counsel), each with their own independent row.
        resp = client_b.post(
            "/api/cases/",
            {"case_number": case_a.case_number, "title": "Someone Else's Version"},
            format="json",
        )
        assert resp.status_code == 201
        case_b_new = Case.objects.get(id=resp.data["id"])
        assert case_b_new.case_number == case_a.case_number
        assert case_b_new.owner_id != case_a.owner_id
        # Both rows now legitimately exist, independently owned.
        assert Case.objects.filter(case_number=case_a.case_number).count() == 2

    def test_create_duplicate_case_number_for_same_user_rejected(self, client_a, case_a):
        resp = client_a.post(
            "/api/cases/",
            {"case_number": case_a.case_number, "title": "My Own Duplicate"},
            format="json",
        )
        assert resp.status_code == 400
        assert "case_number" in resp.data

    def test_create_requires_case_number_and_title(self, client_a):
        resp = client_a.post("/api/cases/", {}, format="json")
        assert resp.status_code == 400
        assert "case_number" in resp.data
        assert "title" in resp.data

    def test_create_cannot_set_tracking_fields(self, client_a):
        # CaseCreateSerializer doesn't expose cnr_number/tracking_config/
        # tracking_enabled at all -- a manually-created case starts
        # untracked, same as before, and gets linked to a CNR later only
        # through the court-tracking preview/confirm flow.
        resp = client_a.post(
            "/api/cases/",
            {
                "case_number": "A-003",
                "title": "New Case",
                "cnr_number": "AB01CD0000112026",
                "tracking_enabled": True,
            },
            format="json",
        )
        assert resp.status_code == 201
        case = Case.objects.get(case_number="A-003")
        assert case.cnr_number is None
        assert case.tracking_enabled is False


@pytest.mark.django_db
class TestHearingIsolation:
    def test_cannot_attach_hearing_to_other_users_case(self, client_a, case_b):
        resp = client_a.post(
            "/api/hearings/",
            {
                "case": case_b.id,
                "hearing_date": "2026-08-01T10:00:00Z",
                "hearing_type": "trial",
            },
            format="json",
        )
        # case_b isn't in client_a's scoped PK queryset for the "case"
        # field, so this must fail validation, not silently attach.
        assert resp.status_code == 400

    def test_list_scoped_by_owner_even_with_case_id_filter(self, user_a, user_b, client_a, case_a, case_b):
        Hearing.objects.create(
            owner=user_a, case=case_a, hearing_date="2026-08-01T10:00:00Z", hearing_type="trial"
        )
        Hearing.objects.create(
            owner=user_b, case=case_b, hearing_date="2026-08-02T10:00:00Z", hearing_type="trial"
        )

        resp = client_a.get("/api/hearings/")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["case"] == case_a.id

        # Even querying explicitly by the other user's case_id must not leak.
        resp = client_a.get(f"/api/hearings/?case_id={case_b.id}")
        assert resp.status_code == 200
        assert resp.data == []

    def test_retrieve_other_users_hearing_404s(self, user_b, client_a, case_b):
        hearing = Hearing.objects.create(
            owner=user_b, case=case_b, hearing_date="2026-08-01T10:00:00Z", hearing_type="trial"
        )
        resp = client_a.get(f"/api/hearings/{hearing.id}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestClientContactIsolation:
    def test_create_ignores_client_supplied_owner(self, client_a, user_a, user_b, case_a):
        resp = client_a.post(
            "/api/client-contacts/",
            {"case": case_a.id, "name": "Someone", "owner": user_b.id},
            format="json",
        )
        assert resp.status_code == 201
        contact = ClientContact.objects.get(id=resp.data["id"])
        assert contact.owner_id == user_a.id

    def test_cannot_attach_contact_to_other_users_case(self, client_a, case_b):
        resp = client_a.post(
            "/api/client-contacts/",
            {"case": case_b.id, "name": "Someone"},
            format="json",
        )
        # case_b isn't in client_a's scoped PK queryset for the "case"
        # field, so this must fail validation, not silently attach.
        assert resp.status_code == 400

    def test_list_scoped_by_owner_even_with_case_id_filter(self, user_a, user_b, client_a, case_a, case_b):
        ClientContact.objects.create(owner=user_a, case=case_a, name="Alice's client")
        ClientContact.objects.create(owner=user_b, case=case_b, name="Bob's client")

        resp = client_a.get("/api/client-contacts/")
        assert resp.status_code == 200
        assert len(resp.data) == 1
        assert resp.data[0]["case"] == case_a.id

        # Even querying explicitly by the other user's case_id must not leak.
        resp = client_a.get(f"/api/client-contacts/?case_id={case_b.id}")
        assert resp.status_code == 200
        assert resp.data == []

    def test_retrieve_other_users_contact_404s(self, user_b, client_a, case_b):
        contact = ClientContact.objects.create(owner=user_b, case=case_b, name="Bob's client")
        resp = client_a.get(f"/api/client-contacts/{contact.id}/")
        assert resp.status_code == 404

    def test_update_other_users_contact_404s(self, user_b, client_a, case_b):
        contact = ClientContact.objects.create(owner=user_b, case=case_b, name="Bob's client")
        resp = client_a.patch(
            f"/api/client-contacts/{contact.id}/", {"name": "Hacked"}, format="json"
        )
        assert resp.status_code == 404
        contact.refresh_from_db()
        assert contact.name == "Bob's client"

    def test_delete_other_users_contact_404s(self, user_b, client_a, case_b):
        contact = ClientContact.objects.create(owner=user_b, case=case_b, name="Bob's client")
        resp = client_a.delete(f"/api/client-contacts/{contact.id}/")
        assert resp.status_code == 404
        assert ClientContact.objects.filter(id=contact.id).exists()


@pytest.mark.django_db
class TestDocumentIsolation:
    def test_cannot_upload_document_against_other_users_case(self, client_a, case_b):
        upload = SimpleUploadedFile("evidence.txt", b"contents", content_type="text/plain")
        resp = client_a.post(
            "/api/documents/upload/",
            {"file": upload, "case_id": case_b.id},
            format="multipart",
        )
        assert resp.status_code == 400

    def test_list_and_detail_scoped_by_owner(self, user_a, user_b, client_a, case_a, case_b):
        doc_a = Document.objects.create(
            owner=user_a, case=case_a, filename="a.txt", file_path="documents/a.txt"
        )
        doc_b = Document.objects.create(
            owner=user_b, case=case_b, filename="b.txt", file_path="documents/b.txt"
        )

        resp = client_a.get("/api/documents/")
        assert resp.status_code == 200
        ids = {d["id"] for d in resp.data}
        assert doc_a.id in ids
        assert doc_b.id not in ids

        resp = client_a.get(f"/api/documents/{doc_b.id}/")
        assert resp.status_code == 404

        resp = client_a.delete(f"/api/documents/{doc_b.id}/")
        assert resp.status_code == 404
        assert Document.objects.filter(id=doc_b.id).exists()


@pytest.mark.django_db
class TestConversationIsolation:
    def test_export_requires_auth_and_ownership(self, user_a, user_b, client_a, case_a, case_b):
        from core.models import Conversation

        convo_b = Conversation.objects.create(owner=user_b, case=case_b, title="Bob's chat")

        # Previously a plain django.views.View with no auth pipeline at all.
        anon = APIClient()
        resp = anon.get(f"/api/conversations/{convo_b.id}/export/")
        assert resp.status_code in (401, 403)

        resp = client_a.get(f"/api/conversations/{convo_b.id}/export/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestAuthEndpoints:
    def test_register_without_token_rejected(self):
        # Self-service signup with no invite is intentionally impossible.
        client = APIClient()
        resp = client.post(
            "/api/auth/register/",
            {"username": "newadvocate", "password": "S0meStrongPass!"},
            format="json",
        )
        assert resp.status_code == 400
        assert not User.objects.filter(username="newadvocate").exists()

    def test_register_with_unknown_token_rejected(self):
        client = APIClient()
        resp = client.post(
            "/api/auth/register/",
            {
                "token": "not-a-real-token",
                "username": "newadvocate",
                "password": "S0meStrongPass!",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert not User.objects.filter(username="newadvocate").exists()

    def test_register_with_valid_token_succeeds_and_consumes_it(self):
        invite = InviteToken.objects.create(email="new@example.com")
        client = APIClient()
        resp = client.post(
            "/api/auth/register/",
            {
                "token": invite.token,
                "username": "newadvocate",
                "password": "S0meStrongPass!",
            },
            format="json",
        )
        assert resp.status_code == 201
        assert User.objects.filter(username="newadvocate").exists()

        invite.refresh_from_db()
        assert invite.used_at is not None
        assert invite.used_by.username == "newadvocate"

        # The now-used token can't mint a second account.
        resp = client.post(
            "/api/auth/register/",
            {
                "token": invite.token,
                "username": "anotheradvocate",
                "password": "An0therStrongPass!",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert not User.objects.filter(username="anotheradvocate").exists()

    def test_register_with_expired_token_rejected(self):
        invite = InviteToken.objects.create(
            expires_at=timezone.now() - timezone.timedelta(hours=1)
        )
        client = APIClient()
        resp = client.post(
            "/api/auth/register/",
            {
                "token": invite.token,
                "username": "newadvocate",
                "password": "S0meStrongPass!",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert not User.objects.filter(username="newadvocate").exists()

    def test_invite_validate_endpoint(self):
        invite = InviteToken.objects.create(email="new@example.com")
        client = APIClient()

        resp = client.get(f"/api/auth/invite/{invite.token}/")
        assert resp.status_code == 200
        assert resp.data == {"valid": True, "reason": None, "email": "new@example.com"}

        resp = client.get("/api/auth/invite/not-a-real-token/")
        assert resp.status_code == 200
        assert resp.data["valid"] is False
        assert resp.data["reason"] == "not_found"

    def test_login_logout_flow(self, user_a):
        client = APIClient()
        resp = client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "alice-pass-123"},
            format="json",
        )
        assert resp.status_code == 200
        token = resp.data["token"]

        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        resp = client.get("/api/cases/")
        assert resp.status_code == 200

        resp = client.post("/api/auth/logout/")
        assert resp.status_code == 204
        assert not Token.objects.filter(key=token).exists()

        # The now-deleted token can no longer authenticate.
        resp = client.get("/api/cases/")
        assert resp.status_code == 401

    def test_login_returns_token(self, user_a):
        client = APIClient()
        resp = client.post(
            "/api/auth/login/",
            {"username": "alice", "password": "alice-pass-123"},
            format="json",
        )
        assert resp.status_code == 200
        assert "token" in resp.data

    def test_endpoints_require_authentication(self):
        anon = APIClient()
        resp = anon.get("/api/cases/")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Case Bot retrieval isolation (POST /api/chat/)
#
# Regression for the Tier-0 bug: a chat with no case_id ran hybrid search
# with no owner filter, so retrieval spanned every tenant's DocumentChunk
# rows and one advocate's chat could surface (and cite) another advocate's
# documents. Retrieval must always be scoped to the requesting user's owner,
# with or without a case_id.
# ---------------------------------------------------------------------------

_FAKE_EMBEDDING = [0.1] * 768
_CHAT_QUERY = "what was the settlement amount"


def _stub_embedding_service():
    """An embedding client that returns a fixed 768-dim vector for anything.

    Every chunk in these tests is stored with the same vector, so cosine
    distance can't be what separates the tenants -- the owner filter is the
    only thing that does. That's the point.
    """
    stub = MagicMock()
    stub.embed_text.return_value = list(_FAKE_EMBEDDING)
    stub.embed_texts.side_effect = lambda texts: [list(_FAKE_EMBEDDING) for _ in texts]
    return stub


def _make_chunk(user, case, text, *, filename):
    """Create a completed Document + one DocumentChunk for `user`.

    Bypasses DocumentProcessor, so the tsvector the keyword leg needs is
    populated here with the same raw SQL the processor uses.
    """
    doc = Document.objects.create(
        owner=user,
        case=case,
        filename=filename,
        file_path=f"documents/{filename}",
        processing_status="completed",
        extracted_text=text,
        chunk_count=1,
    )
    chunk = DocumentChunk.objects.create(
        owner=user,
        document=doc,
        chunk_index=0,
        chunk_text=text,
        embedding=list(_FAKE_EMBEDDING),
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE document_chunks "
            "SET search_vector = to_tsvector('english', chunk_text) WHERE id = %s",
            [chunk.id],
        )
    return doc, chunk


@contextmanager
def _mocked_ai_pipeline():
    """Point the ChatView workflow singleton at mock LLM/embeddings but a
    REAL VectorSearchService + REAL LangGraph, so the owner-scoping in
    hybrid_search is actually exercised. All four attrs are restored on exit.
    """
    llm = MagicMock()
    # Cite every possible [Doc N] label -- citation extraction will only
    # resolve the ones that map to chunks actually retrieved.
    llm.generate.return_value = "Per the record [Doc 1] [Doc 2] [Doc 3] [Doc 4] [Doc 5]."
    search_service = VectorSearchService(
        embedding_service=_stub_embedding_service(), use_reranker=False
    )
    with ExitStack() as stack:
        stack.enter_context(patch.object(chat_view._ai_service, "_llm", llm))
        stack.enter_context(
            patch.object(chat_view._ai_service, "_embedding_service", _stub_embedding_service())
        )
        stack.enter_context(
            patch.object(chat_view._ai_service, "_search_service", search_service)
        )
        stack.enter_context(patch.object(chat_view._ai_service, "_graph", None))
        yield


@pytest.mark.django_db
class TestCaseBotRetrievalIsolation:
    @pytest.fixture
    def chunk_a(self, user_a, case_a):
        return _make_chunk(
            user_a,
            case_a,
            "The settlement amount agreed in Alice's matter was five lakh rupees.",
            filename="alice-settlement.txt",
        )

    @pytest.fixture
    def chunk_b(self, user_b, case_b):
        return _make_chunk(
            user_b,
            case_b,
            "The settlement amount recorded in Bob's matter was ten lakh rupees.",
            filename="bob-settlement.txt",
        )

    # --- VectorSearchService: the retrieval seam itself ---

    def test_search_without_case_id_is_still_owner_scoped(
        self, user_a, user_b, chunk_a, chunk_b
    ):
        _, a = chunk_a
        _, b = chunk_b
        service = VectorSearchService(
            embedding_service=_stub_embedding_service(), use_reranker=False
        )

        a_results = service.search(_CHAT_QUERY, owner_id=user_a.id, case_id=None)
        assert {r.chunk.id for r in a_results} == {a.id}
        assert all(r.chunk.owner_id == user_a.id for r in a_results)

        b_results = service.search(_CHAT_QUERY, owner_id=user_b.id, case_id=None)
        assert {r.chunk.id for r in b_results} == {b.id}

    def test_search_with_case_id_keeps_the_owner_filter(
        self, user_a, case_a, case_b, chunk_a, chunk_b
    ):
        _, a = chunk_a

        # Own case: narrows correctly, returns own chunk.
        own = VectorSearchService(
            embedding_service=_stub_embedding_service(), use_reranker=False
        ).search(_CHAT_QUERY, owner_id=user_a.id, case_id=case_a.id)
        assert {r.chunk.id for r in own} == {a.id}

        # Another tenant's case_id must not act as a back door to their rows.
        leaked = VectorSearchService(
            embedding_service=_stub_embedding_service(), use_reranker=False
        ).search(_CHAT_QUERY, owner_id=user_a.id, case_id=case_b.id)
        assert leaked == []

    def test_search_requires_owner_id(self):
        service = VectorSearchService(
            embedding_service=_stub_embedding_service(), use_reranker=False
        )
        with pytest.raises(ValueError):
            service.search(_CHAT_QUERY, owner_id=None)

    # --- End to end through POST /api/chat/ ---

    def test_chat_with_no_case_id_never_returns_or_cites_another_tenant(
        self, client_a, user_a, chunk_a, chunk_b
    ):
        doc_a, ch_a = chunk_a
        doc_b, ch_b = chunk_b

        with _mocked_ai_pipeline():
            resp = client_a.post("/api/chat/", {"query": _CHAT_QUERY}, format="json")

        assert resp.status_code == 200
        cited_chunk_ids = {c["chunk_id"] for c in resp.data["citations"]}
        cited_doc_ids = {c["document_id"] for c in resp.data["citations"]}

        # The bug: without an owner filter, retrieval + citation would pull
        # in Bob's chunk. It must not.
        assert ch_b.id not in cited_chunk_ids
        assert doc_b.id not in cited_doc_ids
        # Not vacuous: Alice's own chunk WAS retrieved and cited.
        assert cited_chunk_ids == {ch_a.id}

        # Persisted Citation rows are Alice's only, none point at Bob's chunk.
        assert Citation.objects.filter(chunk_id=ch_b.id).count() == 0
        assert all(c.owner_id == user_a.id for c in Citation.objects.all())

    def test_chat_with_own_case_id_still_scopes_correctly(
        self, client_a, case_a, user_a, chunk_a, chunk_b
    ):
        doc_a, ch_a = chunk_a
        doc_b, ch_b = chunk_b

        with _mocked_ai_pipeline():
            resp = client_a.post(
                "/api/chat/",
                {"query": _CHAT_QUERY, "case_id": case_a.id},
                format="json",
            )

        assert resp.status_code == 200
        cited_chunk_ids = {c["chunk_id"] for c in resp.data["citations"]}
        assert cited_chunk_ids == {ch_a.id}
        assert ch_b.id not in cited_chunk_ids

    def test_conversation_without_case_id_keeps_its_case_scope(
        self, client_a, user_a, case_a, chunk_a
    ):
        """Continuing a case's conversation with only conversation_id must
        stay inside that case -- not widen to every document Alice owns."""
        from core.models import Conversation

        _, ch_a = chunk_a
        other_case = Case.objects.create(
            owner=user_a, case_number="A-002", title="Alice's other case"
        )
        _, ch_other = _make_chunk(
            user_a,
            other_case,
            "The settlement amount in Alice's other matter was two lakh rupees.",
            filename="alice-other-settlement.txt",
        )
        convo = Conversation.objects.create(owner=user_a, case=case_a, title="Case A chat")

        with _mocked_ai_pipeline():
            resp = client_a.post(
                "/api/chat/",
                {"query": _CHAT_QUERY, "conversation_id": convo.id},
                format="json",
            )

        assert resp.status_code == 200
        cited_chunk_ids = {c["chunk_id"] for c in resp.data["citations"]}
        assert cited_chunk_ids == {ch_a.id}
        assert ch_other.id not in cited_chunk_ids

    def test_cannot_continue_another_users_conversation(self, client_a, user_b, case_b):
        from core.models import Conversation

        convo_b = Conversation.objects.create(owner=user_b, case=case_b, title="Bob's chat")

        with _mocked_ai_pipeline():
            resp = client_a.post(
                "/api/chat/",
                {"query": _CHAT_QUERY, "conversation_id": convo_b.id},
                format="json",
            )

        assert resp.status_code == 404
        assert not convo_b.messages.exists()


# ---------------------------------------------------------------------------
# Endpoint tenancy coverage (structural guard)
#
# The Case Bot leak shipped because tenancy tests were IDOR-shaped (fetch B's
# row by pk) and nothing forced a new endpoint to get a tenancy review at all.
# This walks every routed core view: each must either inherit
# OwnerScopedMixin, or be listed below as manually reviewed. Adding a plain
# APIView without deciding which list it belongs in (and giving it a tenancy
# test in this file) fails here.
# ---------------------------------------------------------------------------

# AllowAny on purpose. Anything else that sets AllowAny fails the test below.
_PUBLIC_VIEWS = {
    "auth.RegisterView",  # invite-token gated
    "auth.InviteValidateView",  # invite-token gated
    "auth.LoginView",
    "gmail.GmailCallbackView",  # Google's redirect; owner comes from the signed OAuth state
}

# Authenticated, but touch no tenant-owned rows (only request.user itself, or
# public court hierarchy data).
_NO_TENANT_ROWS_VIEWS = {
    "auth.LogoutView",
    "auth.ChangeUsernameView",
    "auth.ChangePasswordView",
    "case_tracking.CourtStructureView",
    "limitation.LimitationRulesView",  # statutory reference data
    "limitation.LimitationComputeView",  # pure computation
}

# Plain APIViews that scope every query to request.user by hand. Reviewed
# 2026-09-15; keep this list in step with a tenancy test per endpoint.
_MANUALLY_SCOPED_VIEWS = {
    "dashboard.DashboardView",
    "dashboard.UpcomingHearingsView",
    "chat.ChatView",
    "conversation.ConversationExportView",
    "court_order.CaseOrdersView",
    "court_order.CourtOrderFileView",
    "limitation.CaseLimitationDeadlineView",
    "hearing_digest.HearingDigestView",
    "hearing_digest.HearingDigestPdfView",
    "hearing_digest.HearingDigestBriefingView",
    "case_tracking.CaseTrackingView",
    "case_tracking.CaseTrackingPreviewView",
    "case_tracking.CaseTrackingConfirmView",
    "case_tracking.CaseTrackingRefreshView",
    "case_tracking.CaseCnrLookupView",
    "case_tracking.CaseCnrCreateView",
    "advocate_search.AdvocateSearchView",
    "advocate_search.AdvocateSearchImportView",
    "advocate_search.AdvocateSearchImportStatusView",
    "advocate_search.AdvocateSearchPreferenceView",
    "advocate_search.AdvocateSearchActiveListView",
    "advocate_search.AdvocateSearchStatusView",
    "advocate_search.AdvocateSearchRetryFailedView",
    "advocate_search.AdvocateSearchCancelView",
    "advocate_profile.AdvocateProfileView",
    "appearance_fee.AppearanceFeeInvoiceView",
    "appearance_fee.AppearanceFeeInvoiceFileView",
    "appearance_fee.AppearanceFeeSendView",
    "appearance_fee.AppearanceFeeMarkPaidView",
    "travel_booking.TravelBookingUploadView",
    "travel_booking.TravelBookingFileView",
    "document.DocumentUploadView",
    "document.DocumentProcessView",
    "document.DocumentDownloadView",
    "gmail.GmailAuthView",
    "gmail.GmailStatusView",
    "gmail.GmailSyncView",
    "gmail.EmailListView",
    "gmail.EmailLinkView",
}


def _routed_core_views():
    from django.urls import URLResolver, get_resolver

    def walk(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns)
            else:
                yield pattern.callback

    views = {}
    for callback in walk(get_resolver().url_patterns):
        view_class = getattr(callback, "view_class", None)
        if view_class is not None and view_class.__module__.startswith("core.views."):
            name = f"{view_class.__module__.rsplit('.', 1)[-1]}.{view_class.__name__}"
            views[name] = view_class
    return views


class TestEndpointTenancyCoverage:
    def test_every_endpoint_is_owner_scoped_or_reviewed(self):
        from core.views.mixins import OwnerScopedMixin

        reviewed = _PUBLIC_VIEWS | _NO_TENANT_ROWS_VIEWS | _MANUALLY_SCOPED_VIEWS
        unreviewed = sorted(
            name
            for name, view_class in _routed_core_views().items()
            if not issubclass(view_class, OwnerScopedMixin) and name not in reviewed
        )
        assert unreviewed == [], (
            "These endpoints neither use OwnerScopedMixin nor appear in a "
            "reviewed tenancy list in test_multi_tenancy.py -- scope them to "
            f"request.user, add a tenancy test, then list them: {unreviewed}"
        )

    def test_only_listed_endpoints_allow_anonymous_access(self):
        from rest_framework.permissions import AllowAny

        anonymous = sorted(
            name
            for name, view_class in _routed_core_views().items()
            if AllowAny in (getattr(view_class, "permission_classes", None) or [])
        )
        assert anonymous == sorted(_PUBLIC_VIEWS)

    def test_reviewed_lists_have_no_stale_entries(self):
        routed = set(_routed_core_views())
        stale = sorted((_PUBLIC_VIEWS | _NO_TENANT_ROWS_VIEWS | _MANUALLY_SCOPED_VIEWS) - routed)
        assert stale == [], f"No longer routed -- remove from the reviewed lists: {stale}"


@pytest.mark.django_db
class TestTaskIsolation:
    def test_list_excludes_other_users_tasks_even_with_their_case_id(
        self, user_a, user_b, client_a, case_a, case_b
    ):
        from core.models import Task

        Task.objects.create(owner=user_a, case=case_a, title="Alice task")
        Task.objects.create(owner=user_b, case=case_b, title="Bob task")

        titles = [t["title"] for t in client_a.get("/api/tasks/").data]
        assert titles == ["Alice task"]

        resp = client_a.get("/api/tasks/", {"case_id": case_b.id})
        assert resp.status_code == 200
        assert resp.data == []

    def test_retrieve_update_delete_other_users_task_404s(self, user_b, client_a, case_b):
        from core.models import Task

        task_b = Task.objects.create(owner=user_b, case=case_b, title="Bob task")

        assert client_a.get(f"/api/tasks/{task_b.id}/").status_code == 404
        assert (
            client_a.patch(f"/api/tasks/{task_b.id}/", {"title": "hijacked"}, format="json").status_code
            == 404
        )
        assert client_a.delete(f"/api/tasks/{task_b.id}/").status_code == 404
        task_b.refresh_from_db()
        assert task_b.title == "Bob task"

    def test_cannot_attach_task_to_other_users_case(self, client_a, case_b):
        resp = client_a.post("/api/tasks/", {"title": "x", "case": case_b.id}, format="json")
        assert resp.status_code == 400
        assert "case" in resp.data

    def test_create_ignores_client_supplied_owner(self, client_a, user_a, user_b):
        from core.models import Task

        resp = client_a.post("/api/tasks/", {"title": "mine", "owner": user_b.id}, format="json")
        assert resp.status_code == 201
        assert Task.objects.get(id=resp.data["id"]).owner == user_a
