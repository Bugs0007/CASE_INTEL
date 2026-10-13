"""Sign in with Google (core/services/google_auth.py, core/views/google_auth.py).

google.oauth2.id_token.verify_oauth2_token is mocked everywhere -- these tests
never call Google. What is exercised for real is everything after it: claim
checks, account matching, username generation, invites, linking and locking.
"""

from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AccountLock, AuthSession, InviteToken, SocialIdentity
from core.services import google_auth

VERIFY = "core.services.google_auth.id_token.verify_oauth2_token"
GOOD_PASSWORD = "Sturdy-pass-9271"


def claims(**overrides):
    base = {
        "iss": "https://accounts.google.com",
        "sub": "g-sub-1",
        "email": "ramesh@gmail.com",
        "email_verified": True,
        "given_name": "Ramesh",
        "family_name": "Kumar",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def configured(settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "test-client.apps.googleusercontent.com"
    settings.SIGNUP_MODE = "open"


@pytest.fixture
def anon():
    return APIClient()


def google_login(client, body=None, **verify_kwargs):
    """POST /api/auth/google/ with the verifier returning `claims()`."""
    payload = {"credential": "fake-id-token", **(body or {})}
    with mock.patch(VERIFY, return_value=claims(**verify_kwargs)):
        return client.post("/api/auth/google/", payload, format="json")


def authed(user):
    from core.tests.auth_helpers import token_for

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token_for(user)}")
    return client


def app_users():
    """Users these tests created -- migration 0014 seeds a 'bhagath' account into every DB."""
    return User.objects.exclude(username="bhagath")


def make_user(username="alice", password=GOOD_PASSWORD, **extra):
    return User.objects.create_user(username=username, password=password, **extra)


@pytest.mark.django_db
class TestGoogleSignIn:
    def test_new_user_created_with_generated_username(self, anon):
        resp = google_login(anon)

        assert resp.status_code == 200, resp.data
        assert resp.data["created"] is True
        assert resp.data["username"] == "ramesh"
        assert set(resp.data) == {"token", "user_id", "username", "created"}
        user = User.objects.get(username="ramesh")
        assert user.email == "ramesh@gmail.com"
        assert (user.first_name, user.last_name) == ("Ramesh", "Kumar")
        assert not user.has_usable_password()
        identity = SocialIdentity.objects.get(user=user)
        assert (identity.provider, identity.subject) == ("google", "g-sub-1")
        session = AuthSession.objects.get(user=user)
        assert session.source == AuthSession.SOURCE_GOOGLE

    def test_issued_token_authenticates(self, anon):
        resp = google_login(anon)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {resp.data['token']}")
        assert client.get("/api/cases/").status_code == 200

    def test_username_collision_gets_numeric_suffix(self, anon):
        make_user("ramesh", email="someone-else@example.com")
        make_user("ramesh2", email="another@example.com")

        resp = google_login(anon)

        assert resp.status_code == 200, resp.data
        assert resp.data["username"] == "ramesh3"

    def test_username_is_cleaned_and_bounded(self):
        assert google_auth.generate_username("Ramesh.K+tag!#@gmail.com") == "ramesh.ktag"
        assert google_auth.generate_username("!!!@gmail.com") == "user"
        long_local = "a" * 400 + "@gmail.com"
        assert len(google_auth.generate_username(long_local)) == 150

    def test_long_username_collision_stays_within_150_chars(self, db):
        User.objects.create_user(username="a" * 150)
        name = google_auth.generate_username("a" * 400 + "@gmail.com")
        assert len(name) <= 150
        assert name.endswith("2")

    def test_concurrent_username_race_is_retried(self, anon):
        """The pre-check says 'ramesh' is free, but another signup commits it
        first: the insert fails with IntegrityError and a fresh pick wins."""
        real = google_auth.generate_username
        calls = []

        def racy(email):
            calls.append(email)
            if len(calls) == 1:
                User.objects.create_user(username="ramesh", email="winner@example.com")
                return "ramesh"
            return real(email)

        with mock.patch.object(google_auth, "generate_username", side_effect=racy):
            resp = google_login(anon)

        assert resp.status_code == 200, resp.data
        assert resp.data["username"] == "ramesh2"
        assert len(calls) == 2

    def test_returning_user_signs_in_by_sub_even_if_google_email_changed(self, anon):
        first = google_login(anon)
        assert first.data["created"] is True

        second = google_login(anon, email="ramesh.new@gmail.com")

        assert second.status_code == 200, second.data
        assert second.data["created"] is False
        assert second.data["user_id"] == first.data["user_id"]
        assert list(app_users().values_list("username", flat=True)) == ["ramesh"]
        identity = SocialIdentity.objects.get()
        assert identity.email == "ramesh.new@gmail.com"
        assert identity.last_login_at is not None

    def test_email_matching_existing_account_is_409_and_creates_nothing(self, anon):
        make_user("old-ramesh", email="Ramesh@Gmail.com")

        resp = google_login(anon)

        assert resp.status_code == 409
        assert resp.data["code"] == "account_exists"
        assert "connect Google from Settings" in resp.data["detail"]
        assert app_users().count() == 1
        assert not SocialIdentity.objects.exists()
        assert not AuthSession.objects.exists()

    def test_unverified_email_is_rejected(self, anon):
        resp = google_login(anon, email_verified=False)
        assert resp.status_code == 401
        assert resp.data["code"] == "google_token_invalid"
        assert not app_users().exists()

    def test_wrong_issuer_is_rejected(self, anon):
        resp = google_login(anon, iss="https://evil.example.com")
        assert resp.status_code == 401
        assert resp.data["code"] == "google_token_invalid"

    def test_bare_google_issuer_is_accepted(self, anon):
        assert google_login(anon, iss="accounts.google.com").status_code == 200

    def test_verifier_valueerror_is_401(self, anon):
        with mock.patch(VERIFY, side_effect=ValueError("Token expired")):
            resp = anon.post("/api/auth/google/", {"credential": "x"}, format="json")
        assert resp.status_code == 401
        assert resp.data["code"] == "google_token_invalid"

    def test_missing_credential_is_401_without_calling_google(self, anon):
        with mock.patch(VERIFY) as verify:
            resp = anon.post("/api/auth/google/", {}, format="json")
        assert resp.status_code == 401
        verify.assert_not_called()

    def test_verifier_called_with_configured_audience(self, anon, settings):
        with mock.patch(VERIFY, return_value=claims()) as verify:
            anon.post("/api/auth/google/", {"credential": "tok"}, format="json")
        args = verify.call_args.args
        assert args[0] == "tok"
        assert args[2] == settings.GOOGLE_OAUTH_CLIENT_ID

    def test_credential_is_never_logged(self, anon, caplog):
        caplog.set_level("DEBUG")
        with mock.patch(VERIFY, side_effect=ValueError("bad token SECRET-CREDENTIAL")):
            anon.post("/api/auth/google/", {"credential": "SECRET-CREDENTIAL"}, format="json")
        assert "SECRET-CREDENTIAL" not in caplog.text

    def test_inactive_user_is_blocked(self, anon):
        first = google_login(anon)
        User.objects.filter(pk=first.data["user_id"]).update(is_active=False)

        resp = google_login(anon)

        assert resp.status_code == 403
        assert resp.data["code"] == "account_disabled"

    def test_empty_client_id_returns_503(self, anon, settings):
        settings.GOOGLE_OAUTH_CLIENT_ID = ""
        with mock.patch(VERIFY) as verify:
            resp = anon.post("/api/auth/google/", {"credential": "x"}, format="json")
        assert resp.status_code == 503
        assert resp.data["code"] == "google_not_configured"
        verify.assert_not_called()


@pytest.mark.django_db
class TestInviteMode:
    @pytest.fixture(autouse=True)
    def invite_mode(self, settings):
        settings.SIGNUP_MODE = "invite"

    def test_blocked_without_a_token(self, anon):
        resp = google_login(anon)
        assert resp.status_code == 403
        assert resp.data["code"] == "invite_required"
        assert not app_users().exists()

    def test_blocked_with_an_unknown_or_spent_token(self, anon):
        spent = InviteToken.objects.create(used_at=timezone.now())
        for token in ("nope", spent.token):
            resp = google_login(anon, {"invite_token": token})
            assert resp.status_code == 403
            assert resp.data["code"] == "invite_required"
        expired = InviteToken.objects.create(expires_at=timezone.now() - timedelta(days=1))
        assert google_login(anon, {"invite_token": expired.token}).status_code == 403
        assert not app_users().exists()

    def test_works_with_a_valid_token_and_consumes_it(self, anon):
        invite = InviteToken.objects.create()

        resp = google_login(anon, {"invite_token": invite.token})

        assert resp.status_code == 200, resp.data
        assert resp.data["created"] is True
        invite.refresh_from_db()
        assert invite.used_at is not None
        assert invite.used_by_id == resp.data["user_id"]
        # Single use: the same invite can't mint a second account.
        again = google_login(anon, {"invite_token": invite.token}, sub="g-sub-2", email="other@gmail.com")
        assert again.status_code == 403

    def test_returning_user_needs_no_invite(self, anon):
        invite = InviteToken.objects.create()
        google_login(anon, {"invite_token": invite.token})

        resp = google_login(anon)

        assert resp.status_code == 200
        assert resp.data["created"] is False

    def test_open_mode_consumes_a_passed_invite_but_does_not_need_one(self, anon, settings):
        settings.SIGNUP_MODE = "open"
        invite = InviteToken.objects.create()
        assert google_login(anon, {"invite_token": invite.token}).status_code == 200
        invite.refresh_from_db()
        assert invite.used_at is not None

        stale = google_login(anon, {"invite_token": "garbage"}, sub="g-sub-2", email="b@gmail.com")
        assert stale.status_code == 200


@pytest.mark.django_db
class TestLinking:
    def test_link_then_sign_in_with_google(self, anon):
        user = make_user(email="alice@example.com")
        client = authed(user)

        with mock.patch(VERIFY, return_value=claims(email="alice.work@gmail.com")):
            resp = client.post("/api/auth/google/link/", {"credential": "x"}, format="json")
        assert resp.status_code == 201, resp.data
        assert resp.data["google_email"] == "alice.work@gmail.com"

        signed_in = google_login(anon, email="alice.work@gmail.com")
        assert signed_in.status_code == 200
        assert signed_in.data["user_id"] == user.pk
        assert signed_in.data["created"] is False

    def test_unlink_happy_path(self):
        user = make_user()
        SocialIdentity.objects.create(user=user, provider="google", subject="s1", email="a@gmail.com")

        resp = authed(user).delete("/api/auth/google/link/")

        assert resp.status_code == 204
        assert not SocialIdentity.objects.filter(user=user).exists()

    def test_unlink_when_nothing_linked_is_404(self):
        assert authed(make_user()).delete("/api/auth/google/link/").status_code == 404

    def test_link_conflict_google_account_belongs_to_someone_else(self):
        other = make_user("bob")
        SocialIdentity.objects.create(user=other, provider="google", subject="g-sub-1", email="r@gmail.com")
        user = make_user()

        with mock.patch(VERIFY, return_value=claims()):
            resp = authed(user).post("/api/auth/google/link/", {"credential": "x"}, format="json")

        assert resp.status_code == 409
        assert resp.data["code"] == "google_account_taken"
        assert not SocialIdentity.objects.filter(user=user).exists()

    def test_link_conflict_user_already_has_google(self):
        user = make_user()
        SocialIdentity.objects.create(user=user, provider="google", subject="old", email="a@gmail.com")

        with mock.patch(VERIFY, return_value=claims(sub="different")):
            resp = authed(user).post("/api/auth/google/link/", {"credential": "x"}, format="json")

        assert resp.status_code == 409
        assert resp.data["code"] == "already_linked"
        assert SocialIdentity.objects.get(user=user).subject == "old"

    def test_link_requires_authentication(self, anon):
        with mock.patch(VERIFY, return_value=claims()):
            resp = anon.post("/api/auth/google/link/", {"credential": "x"}, format="json")
        assert resp.status_code == 401

    def test_unlink_refused_without_a_usable_password(self, anon):
        created = google_login(anon)
        user = User.objects.get(pk=created.data["user_id"])

        resp = authed(user).delete("/api/auth/google/link/")

        assert resp.status_code == 400
        assert resp.data["code"] == "no_password"
        assert SocialIdentity.objects.filter(user=user).exists()

    def test_link_with_invalid_credential_is_401(self):
        with mock.patch(VERIFY, side_effect=ValueError("bad")):
            resp = authed(make_user()).post("/api/auth/google/link/", {"credential": "x"}, format="json")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestCredentialsLocked:
    @pytest.fixture
    def locked(self):
        user = make_user("demo")
        AccountLock.objects.create(user=user, credentials_locked=True)
        return user

    def test_cannot_link(self, locked):
        with mock.patch(VERIFY, return_value=claims()) as verify:
            resp = authed(locked).post("/api/auth/google/link/", {"credential": "x"}, format="json")
        assert resp.status_code == 403
        assert resp.data["code"] == "credentials_locked"
        verify.assert_not_called()
        assert not SocialIdentity.objects.exists()

    def test_cannot_unlink(self, locked):
        SocialIdentity.objects.create(user=locked, provider="google", subject="s", email="a@gmail.com")
        resp = authed(locked).delete("/api/auth/google/link/")
        assert resp.status_code == 403
        assert resp.data["code"] == "credentials_locked"
        assert SocialIdentity.objects.filter(user=locked).exists()

    def test_cannot_set_a_password(self):
        user = User.objects.create_user(username="demo2")
        user.set_unusable_password()
        user.save()
        AccountLock.objects.create(user=user, credentials_locked=True)

        resp = authed(user).post("/api/auth/set-password/", {"new_password": GOOD_PASSWORD}, format="json")

        assert resp.status_code == 403
        assert resp.data["code"] == "credentials_locked"
        user.refresh_from_db()
        assert not user.has_usable_password()


@pytest.mark.django_db
class TestSetPassword:
    @pytest.fixture
    def google_only(self, anon):
        resp = google_login(anon)
        return User.objects.get(pk=resp.data["user_id"]), resp.data["token"]

    def test_sets_password_keeps_this_session_revokes_others(self, google_only, anon):
        user, token = google_only
        other = google_login(anon)  # a second device
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

        resp = client.post("/api/auth/set-password/", {"new_password": GOOD_PASSWORD}, format="json")

        assert resp.status_code == 200, resp.data
        assert resp.data["revoked"] == 1
        user.refresh_from_db()
        assert user.check_password(GOOD_PASSWORD)
        assert client.get("/api/cases/").status_code == 200
        stale = APIClient()
        stale.credentials(HTTP_AUTHORIZATION=f"Token {other.data['token']}")
        assert stale.get("/api/cases/").status_code == 401

    def test_password_then_works_for_login_and_unlinking(self, google_only, anon):
        user, token = google_only
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        client.post("/api/auth/set-password/", {"new_password": GOOD_PASSWORD}, format="json")

        login = anon.post(
            "/api/auth/login/", {"username": user.username, "password": GOOD_PASSWORD}, format="json"
        )
        assert login.status_code == 200
        assert client.delete("/api/auth/google/link/").status_code == 204

    def test_weak_password_rejected(self, google_only):
        user, token = google_only
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        resp = client.post("/api/auth/set-password/", {"new_password": "123"}, format="json")
        assert resp.status_code == 400
        assert "new_password" in resp.data
        user.refresh_from_db()
        assert not user.has_usable_password()

    def test_refused_when_a_password_already_exists(self):
        user = make_user()
        resp = authed(user).post("/api/auth/set-password/", {"new_password": "Another-pass-5521"}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "has_password"
        user.refresh_from_db()
        assert user.check_password(GOOD_PASSWORD)


@pytest.mark.django_db
class TestMe:
    def test_password_account_without_google(self):
        user = make_user(email="alice@example.com")
        data = authed(user).get("/api/auth/me/").data
        assert data == {
            "id": user.pk,
            "username": "alice",
            "email": "alice@example.com",
            "has_password": True,
            "google_linked": False,
            "google_email": None,
            "credentials_locked": False,
        }

    def test_google_account_and_locked_flag(self, anon):
        created = google_login(anon)
        user = User.objects.get(pk=created.data["user_id"])
        AccountLock.objects.create(user=user, credentials_locked=True)

        data = authed(user).get("/api/auth/me/").data

        assert data["has_password"] is False
        assert data["google_linked"] is True
        assert data["google_email"] == "ramesh@gmail.com"
        assert data["credentials_locked"] is True

    def test_requires_authentication(self, anon):
        assert anon.get("/api/auth/me/").status_code == 401
