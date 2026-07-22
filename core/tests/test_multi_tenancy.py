"""Row-level multi-tenancy isolation tests.

Two independent advocates (user_a/user_b), each with their own Case. For
every endpoint that touches Case (or something hanging off it), user A must
never be able to list, retrieve, update, or delete anything owned by user B.
"""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Case, Document, Hearing


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

    def test_create_ignores_client_supplied_owner(self, client_a, user_a, user_b):
        resp = client_a.post(
            "/api/cases/",
            {
                "case_number": "A-002",
                "title": "New Case",
                "client_name": "Someone",
                "owner": user_b.id,
            },
            format="json",
        )
        assert resp.status_code == 201
        case = Case.objects.get(id=resp.data["id"])
        assert case.owner_id == user_a.id


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
    def test_register_login_logout_flow(self):
        client = APIClient()

        resp = client.post(
            "/api/auth/register/",
            {"username": "newadvocate", "password": "S0meStrongPass!"},
            format="json",
        )
        assert resp.status_code == 201
        token = resp.data["token"]
        assert User.objects.filter(username="newadvocate").exists()

        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        resp = client.get("/api/cases/")
        assert resp.status_code == 200
        assert resp.data == []

        resp = client.post("/api/auth/logout/")
        assert resp.status_code == 204
        assert not Token.objects.filter(key=token).exists()

        # The now-deleted token can no longer authenticate.
        resp = client.get("/api/cases/")
        assert resp.status_code == 401

    def test_register_rejects_duplicate_username(self, user_a):
        client = APIClient()
        resp = client.post(
            "/api/auth/register/",
            {"username": user_a.username, "password": "S0meStrongPass!"},
            format="json",
        )
        assert resp.status_code == 400

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
