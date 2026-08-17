"""Tests for the admin-controlled account lock (Phase E) and the
self-service username/password change it protects (Phase D).

Covers: a locked account rejects both changes via the API even with a
valid session and correct current password; an unlocked account can
change normally; a superuser can toggle the lock through the real Django
admin User page; a non-staff user cannot reach that page at all.
"""

import re

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import AccountLock
from core.services.account_security import is_credentials_locked


def _authed_api_client(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def user():
    u = User.objects.create_user(username="lockable-user", password="CorrectHorse123!")
    return u


@pytest.fixture
def api(user):
    return _authed_api_client(user)


@pytest.mark.django_db
class TestChangeUsernameAndPassword:
    def test_unlocked_user_can_change_username(self, api, user):
        resp = api.post(
            "/api/auth/change-username/",
            {"current_password": "CorrectHorse123!", "new_username": "new-handle"},
            format="json",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.username == "new-handle"

    def test_username_change_requires_correct_current_password(self, api, user):
        resp = api.post(
            "/api/auth/change-username/",
            {"current_password": "wrong-password", "new_username": "new-handle"},
            format="json",
        )
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.username == "lockable-user"

    def test_username_change_rejects_a_name_already_taken(self, api, user):
        User.objects.create_user(username="already-taken", password="x")
        resp = api.post(
            "/api/auth/change-username/",
            {"current_password": "CorrectHorse123!", "new_username": "already-taken"},
            format="json",
        )
        assert resp.status_code == 400

    def test_unlocked_user_can_change_password(self, api, user):
        old_token = Token.objects.get(user=user).key

        resp = api.post(
            "/api/auth/change-password/",
            {"current_password": "CorrectHorse123!", "new_password": "Br4nd-N3w-Passw0rd!"},
            format="json",
        )
        assert resp.status_code == 200
        new_token = resp.data["token"]
        assert new_token != old_token

        user.refresh_from_db()
        assert user.check_password("Br4nd-N3w-Passw0rd!")
        # The old token must no longer authenticate anything.
        assert not Token.objects.filter(key=old_token).exists()

    def test_password_change_requires_correct_current_password(self, api, user):
        resp = api.post(
            "/api/auth/change-password/",
            {"current_password": "wrong-password", "new_password": "Br4nd-N3w-Passw0rd!"},
            format="json",
        )
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.check_password("CorrectHorse123!")

    def test_password_change_enforces_django_validators(self, api, user):
        resp = api.post(
            "/api/auth/change-password/",
            {"current_password": "CorrectHorse123!", "new_password": "12345678"},
            format="json",
        )
        assert resp.status_code == 400
        user.refresh_from_db()
        assert user.check_password("CorrectHorse123!")

    def test_unauthenticated_request_is_rejected(self, user):
        anon = APIClient()
        resp = anon.post(
            "/api/auth/change-password/",
            {"current_password": "CorrectHorse123!", "new_password": "Br4nd-N3w-Passw0rd!"},
            format="json",
        )
        assert resp.status_code == 401


@pytest.mark.django_db
class TestAccountLockBlocksSelfServiceChanges:
    def test_locked_account_rejects_username_change_with_valid_session_and_correct_password(
        self, api, user
    ):
        AccountLock.objects.create(user=user, credentials_locked=True)

        resp = api.post(
            "/api/auth/change-username/",
            {"current_password": "CorrectHorse123!", "new_username": "new-handle"},
            format="json",
        )

        assert resp.status_code == 403
        assert resp.data["code"] == "credentials_locked"
        user.refresh_from_db()
        assert user.username == "lockable-user"

    def test_locked_account_rejects_password_change_with_valid_session_and_correct_password(
        self, api, user
    ):
        AccountLock.objects.create(user=user, credentials_locked=True)

        resp = api.post(
            "/api/auth/change-password/",
            {"current_password": "CorrectHorse123!", "new_password": "Br4nd-N3w-Passw0rd!"},
            format="json",
        )

        assert resp.status_code == 403
        assert resp.data["code"] == "credentials_locked"
        user.refresh_from_db()
        assert user.check_password("CorrectHorse123!")

    def test_lock_flag_false_does_not_block(self, api, user):
        """A row exists but credentials_locked=False -- must behave
        exactly like no row at all."""
        AccountLock.objects.create(user=user, credentials_locked=False)

        resp = api.post(
            "/api/auth/change-username/",
            {"current_password": "CorrectHorse123!", "new_username": "new-handle"},
            format="json",
        )

        assert resp.status_code == 200

    def test_is_credentials_locked_false_when_no_row_exists(self, user):
        assert is_credentials_locked(user) is False

    def test_is_credentials_locked_true_when_locked(self, user):
        AccountLock.objects.create(user=user, credentials_locked=True)
        assert is_credentials_locked(user) is True


def _scrape_and_fill_form(html: str, overrides: dict) -> dict:
    """Extracts every field Django's admin changeform actually rendered
    (main form + inline formsets, including the management-form hidden
    inputs) and applies `overrides` on top -- the realistic way to test
    an admin POST without hardcoding a guessed inline-formset prefix,
    which is exactly the kind of guess this project's own conventions
    (see CLAUDE.md / recent CNR-parsing fixes) explicitly avoid."""
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form", id="user_form")
    assert form is not None, "Could not find the admin User changeform -- page structure changed?"

    data: dict[str, str] = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        input_type = (inp.get("type") or "text").lower()
        if input_type == "checkbox":
            if inp.has_attr("checked"):
                data[name] = inp.get("value", "on")
        elif input_type == "radio":
            if inp.has_attr("checked"):
                data[name] = inp.get("value", "")
        else:
            data[name] = inp.get("value", "")

    for select in form.find_all("select"):
        name = select.get("name")
        if not name:
            continue
        selected = select.find_all("option", selected=True)
        if select.has_attr("multiple"):
            data[name] = [o.get("value", "") for o in selected]
        else:
            data[name] = selected[0].get("value", "") if selected else ""

    for textarea in form.find_all("textarea"):
        name = textarea.get("name")
        if name:
            data[name] = textarea.text or ""

    data.update(overrides)
    return data


@pytest.mark.django_db
class TestAccountLockDjangoAdminAccessControl:
    """The lock is only ever toggle-able from the real Django admin User
    page -- there is deliberately no API for it. These drive that exact
    page (scraping the real rendered form rather than guessing its field
    names) to prove a superuser can flip it and a non-staff user can't
    even reach the page."""

    @pytest.fixture
    def superuser(self):
        return User.objects.create_superuser(username="admin-super", password="x", email="")

    @pytest.fixture
    def target_user(self):
        return User.objects.create_user(username="recruiter-lookalike", password="x")

    def test_superuser_can_lock_account_via_real_admin_page(self, client, superuser, target_user):
        client.force_login(superuser)
        url = reverse("admin:auth_user_change", args=[target_user.id])

        get_resp = client.get(url)
        assert get_resp.status_code == 200

        prefix_match = re.search(r'name="([a-zA-Z0-9_]+)-TOTAL_FORMS"', get_resp.content.decode())
        assert prefix_match, "Could not find the AccountLock inline's formset prefix in the rendered admin page"
        prefix = prefix_match.group(1)

        data = _scrape_and_fill_form(
            get_resp.content.decode(),
            {f"{prefix}-0-credentials_locked": "on"},
        )

        post_resp = client.post(url, data=data, follow=True)
        assert post_resp.status_code == 200
        assert is_credentials_locked(target_user) is True

    def test_superuser_can_unlock_account_via_real_admin_page(self, client, superuser, target_user):
        AccountLock.objects.create(user=target_user, credentials_locked=True)
        client.force_login(superuser)
        url = reverse("admin:auth_user_change", args=[target_user.id])

        get_resp = client.get(url)
        prefix_match = re.search(r'name="([a-zA-Z0-9_]+)-TOTAL_FORMS"', get_resp.content.decode())
        prefix = prefix_match.group(1)

        data = _scrape_and_fill_form(get_resp.content.decode(), {})
        # Unchecking a checkbox means simply not submitting it -- remove it if present.
        data.pop(f"{prefix}-0-credentials_locked", None)

        client.post(url, data=data, follow=True)

        assert is_credentials_locked(target_user) is False

    def test_non_staff_user_cannot_reach_the_admin_page(self, client, target_user):
        other = User.objects.create_user(username="not-an-admin", password="x")
        client.force_login(other)
        url = reverse("admin:auth_user_change", args=[target_user.id])

        resp = client.get(url)

        assert resp.status_code in (302, 403)
        if resp.status_code == 302:
            assert "/admin/login" in resp.url

    def test_non_staff_user_cannot_toggle_lock_even_by_posting_directly(self, client, target_user):
        other = User.objects.create_user(username="not-an-admin-2", password="x")
        client.force_login(other)
        url = reverse("admin:auth_user_change", args=[target_user.id])

        client.post(url, data={"account_lock-0-credentials_locked": "on"}, follow=True)

        assert is_credentials_locked(target_user) is False
