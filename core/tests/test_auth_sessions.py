"""Per-session, expiring tokens (core/models/auth_session.py).

What broke before: one permanent token per user, shared by every device,
so a logout anywhere signed everyone out (the shared recruiter account kept
bouncing to /login) and a leaked token never expired.
"""

import hashlib
import importlib
from datetime import timedelta

import pytest
from django.apps import apps as global_apps
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import AuthSession
from core.services import auth_sessions


@pytest.fixture
def user(db):
    return User.objects.create_user(username="session-user", password="Pass-word-123")


def _login(username="session-user", password="Pass-word-123", agent="test-agent"):
    client = APIClient(HTTP_USER_AGENT=agent)
    resp = client.post("/api/auth/login/", {"username": username, "password": password}, format="json")
    assert resp.status_code == 200, resp.data
    client.credentials(HTTP_AUTHORIZATION=f"Token {resp.data['token']}")
    return client, resp.data["token"]


@pytest.mark.django_db
class TestSessions:
    def test_each_login_is_its_own_session(self, user):
        laptop, laptop_key = _login(agent="laptop")
        phone, phone_key = _login(agent="phone")

        assert laptop_key != phone_key
        assert AuthSession.objects.filter(user=user).count() == 2
        assert laptop.get("/api/cases/").status_code == 200
        assert phone.get("/api/cases/").status_code == 200

    def test_logout_ends_only_that_session(self, user):
        laptop, _ = _login(agent="laptop")
        phone, _ = _login(agent="phone")

        assert laptop.post("/api/auth/logout/").status_code == 204

        assert laptop.get("/api/cases/").status_code == 401
        assert phone.get("/api/cases/").status_code == 200  # still signed in

    def test_only_a_hash_of_the_key_is_stored(self, user):
        _, key = _login()
        session = AuthSession.objects.get(user=user)
        assert session.key_hash == hashlib.sha256(key.encode()).hexdigest()
        assert key not in {session.key_hash, session.user_agent}

    def test_an_idle_session_expires(self, user):
        client, _ = _login()
        AuthSession.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(seconds=1)
        )
        resp = client.get("/api/cases/")
        assert resp.status_code == 401  # 401, not 403: the frontend keys on it

    def test_use_slides_the_window(self, user, settings):
        settings.AUTH_SESSION_IDLE_DAYS = 7
        client, _ = _login()
        long_ago = timezone.now() - timedelta(days=6)
        AuthSession.objects.filter(user=user).update(last_used_at=long_ago, expires_at=long_ago + timedelta(days=7))

        assert client.get("/api/cases/").status_code == 200

        session = AuthSession.objects.get(user=user)
        assert session.expires_at > timezone.now() + timedelta(days=6, hours=23)

    def test_a_deactivated_user_is_signed_out(self, user):
        client, _ = _login()
        User.objects.filter(id=user.id).update(is_active=False)
        assert client.get("/api/cases/").status_code == 401

    def test_no_credentials_is_a_401(self, db):
        assert APIClient().get("/api/cases/").status_code == 401

    def test_password_change_ends_every_other_session(self, user):
        laptop, _ = _login(agent="laptop")
        phone, _ = _login(agent="phone")

        resp = laptop.post(
            "/api/auth/change-password/",
            {"current_password": "Pass-word-123", "new_password": "Br4nd-N3w-Passw0rd!"},
            format="json",
        )

        assert resp.status_code == 200
        assert phone.get("/api/cases/").status_code == 401
        assert laptop.get("/api/cases/").status_code == 401  # swap to the new token
        laptop.credentials(HTTP_AUTHORIZATION=f"Token {resp.data['token']}")
        assert laptop.get("/api/cases/").status_code == 200


@pytest.mark.django_db
class TestSessionList:
    def test_lists_own_sessions_and_flags_this_one(self, user):
        laptop, _ = _login(agent="laptop")
        _login(agent="phone")

        rows = laptop.get("/api/auth/sessions/").data

        assert sorted(r["user_agent"] for r in rows) == ["laptop", "phone"]
        assert [r["user_agent"] for r in rows if r["current"]] == ["laptop"]
        assert "key_hash" not in rows[0]

    def test_revoke_one_session(self, user):
        laptop, _ = _login(agent="laptop")
        phone, _ = _login(agent="phone")
        phone_id = next(r["id"] for r in laptop.get("/api/auth/sessions/").data if r["user_agent"] == "phone")

        assert laptop.delete(f"/api/auth/sessions/{phone_id}/").status_code == 204

        assert phone.get("/api/cases/").status_code == 401
        assert laptop.get("/api/cases/").status_code == 200

    def test_revoke_all_others(self, user):
        laptop, _ = _login(agent="laptop")
        phone, _ = _login(agent="phone")
        tablet, _ = _login(agent="tablet")

        resp = laptop.post("/api/auth/sessions/revoke-others/")

        assert resp.data == {"revoked": 2}
        assert phone.get("/api/cases/").status_code == 401
        assert tablet.get("/api/cases/").status_code == 401
        assert laptop.get("/api/cases/").status_code == 200

    def test_another_users_sessions_are_invisible_and_untouchable(self, user):
        User.objects.create_user(username="someone-else", password="Other-pass-123")
        mine, _ = _login()
        theirs, _ = _login("someone-else", "Other-pass-123")
        their_id = AuthSession.objects.get(user__username="someone-else").id

        assert all(r["id"] != their_id for r in mine.get("/api/auth/sessions/").data)
        assert mine.delete(f"/api/auth/sessions/{their_id}/").status_code == 404
        assert theirs.get("/api/cases/").status_code == 200

    def test_ended_sessions_are_pruned_at_the_next_sign_in(self, user):
        _, _ = _login()
        AuthSession.objects.filter(user=user).update(revoked_at=timezone.now() - timedelta(days=40))
        _login()
        assert AuthSession.objects.filter(user=user).count() == 1


_carry_over = importlib.import_module("core.migrations.0041_carry_over_auth_tokens")


@pytest.mark.django_db
class TestExistingSignInsSurviveTheSwitch:
    def test_a_browser_holding_the_old_token_stays_signed_in(self, user):
        """No one is logged out by the deploy: 0041 turns each old token
        into a session with the same key."""
        old = Token.objects.create(user=user)

        _carry_over.carry_over(global_apps, None)

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {old.key}")
        assert client.get("/api/cases/").status_code == 200
        session = AuthSession.objects.get(user=user)
        assert session.source == AuthSession.SOURCE_LEGACY
        # ...and from now on it can be ended like any other session.
        assert client.post("/api/auth/logout/").status_code == 204
        assert client.get("/api/cases/").status_code == 401

    def test_the_old_token_alone_no_longer_authenticates(self, user):
        """Without the carry-over (a token created after the migration),
        DRF's permanent tokens are not accepted at all any more."""
        stray = Token.objects.create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {stray.key}")
        assert client.get("/api/cases/").status_code == 401

    def test_carry_over_is_idempotent(self, user):
        Token.objects.create(user=user)
        _carry_over.carry_over(global_apps, None)
        _carry_over.carry_over(global_apps, None)
        assert AuthSession.objects.filter(user=user).count() == 1


def test_sessions_expire_after_the_configured_idle_days(settings):
    settings.AUTH_SESSION_IDLE_DAYS = 3
    assert auth_sessions.idle_window() == timedelta(days=3)
