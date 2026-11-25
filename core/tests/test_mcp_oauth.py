"""The OAuth 2.1 authorization server for the MCP connector (django-oauth-toolkit
plus core/services/oauth_policy.py and core/views/oauth.py)."""

import base64
import hashlib
import html
import json
import re
import secrets
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from django.test import Client
from oauth2_provider.models import get_access_token_model, get_application_model, get_refresh_token_model
from rest_framework.test import APIClient

from core.services.oauth_policy import redirect_allowed_by_policy
from core.tests.auth_helpers import token_for
from core.tests.mcp_support import ISSUER, RESOURCE, _mcp_settings, make_tenant, mint_token  # noqa: F401

pytestmark = pytest.mark.django_db

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
LOOPBACK = "http://127.0.0.1:53682/callback"


@pytest.fixture(autouse=True)
def _issuer(settings):
    settings.ALLOWED_HOSTS = ["testserver", "api.caseintel.test"]
    from oauth2_provider.settings import oauth2_settings

    original = oauth2_settings.OIDC_ISS_ENDPOINT
    oauth2_settings.OIDC_ISS_ENDPOINT = ISSUER
    yield
    oauth2_settings.OIDC_ISS_ENDPOINT = original


@pytest.fixture
def tenant():
    t = make_tenant("oauth_a", "Ramesh")
    t.password = "Pw-" + secrets.token_hex(8)
    t.user.set_password(t.password)
    t.user.save()
    return t


def register(client, redirect_uris, **extra):
    body = {"client_name": "Claude", "redirect_uris": redirect_uris, "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"], **extra}
    return client.post("/oauth/register/", data=json.dumps(body), content_type="application/json")


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize_params(client_id, challenge, redirect=LOOPBACK, scope="cases:read", resource=RESOURCE):
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect, "scope": scope,
              "state": "s1", "code_challenge": challenge, "code_challenge_method": "S256"}
    if resource:
        params["resource"] = resource
    return params


def sign_in(client, tenant, next_url=""):
    return client.post("/oauth/login/", {"username": tenant.user.username, "password": tenant.password,
                                         "next": next_url})


def consent(client, params):
    page = client.get(f"/oauth/authorize/?{urlencode(params)}")
    assert page.status_code == 200, page.content[:500]
    text = page.content.decode()
    hidden = {k: html.unescape(v) for k, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', text)}
    hidden["allow"] = "Authorize"
    return text, client.post(f"/oauth/authorize/?{urlencode(params)}", hidden)


def full_flow(tenant, redirect=LOOPBACK, scope="cases:read cases:write"):
    client = Client()
    client_id = register(client, [redirect]).json()["client_id"]
    verifier, challenge = pkce()
    params = authorize_params(client_id, challenge, redirect=redirect, scope=scope)
    sign_in(client, tenant)
    _, r = consent(client, params)
    code = parse_qs(urlsplit(r["Location"]).query)["code"][0]
    tok = client.post("/oauth/token/", {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect,
                                        "client_id": client_id, "code_verifier": verifier, "resource": RESOURCE})
    return client, client_id, tok


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_authorization_server_metadata():
    m = Client().get("/.well-known/oauth-authorization-server").json()
    assert m["issuer"] == ISSUER
    assert m["authorization_endpoint"].endswith("/oauth/authorize/")
    assert m["token_endpoint"].endswith("/oauth/token/")
    assert m["registration_endpoint"].endswith("/oauth/register/")
    assert m["client_id_metadata_document_supported"] is True
    assert "none" in m["token_endpoint_auth_methods_supported"]
    assert m["code_challenge_methods_supported"] == ["S256"]
    assert m["authorization_response_iss_parameter_supported"] is True
    assert m["response_types_supported"] == ["code"]
    assert set(m["grant_types_supported"]) == {"authorization_code", "refresh_token"}
    assert set(m["scopes_supported"]) == {"cases:read", "cases:write"}


# ---------------------------------------------------------------------------
# Redirect URIs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri,allowed",
    [
        (CLAUDE_CALLBACK, True),
        ("http://localhost:6274/oauth/callback", True),
        ("http://127.0.0.1:33418/callback", True),
        ("http://127.0.0.1/callback", True),
        ("https://claude.ai/api/mcp/auth_callback/evil", False),
        ("https://evil.example/cb", False),
        ("http://localhost.evil.example/cb", False),
        ("http://user@127.0.0.1:8000/cb", False),
        ("https://127.0.0.1:8000/cb", False),
        ("http://127.0.0.1:8000/cb#frag", False),
        ("javascript:alert(1)", False),
        ("", False),
    ],
)
def test_redirect_policy(uri, allowed):
    assert redirect_allowed_by_policy(uri) is allowed


def test_dcr_accepts_claude_and_loopback_and_rejects_others():
    c = Client()
    assert register(c, [CLAUDE_CALLBACK]).status_code == 201
    assert register(c, [LOOPBACK]).status_code == 201
    assert register(c, ["https://evil.example/cb"]).status_code in (401, 403)
    assert register(c, [CLAUDE_CALLBACK, "https://evil.example/cb"]).status_code in (401, 403)
    assert register(c, [LOOPBACK], grant_types=["client_credentials"]).status_code in (401, 403)
    assert register(c, []).status_code in (400, 401, 403)


def test_loopback_redirect_matches_any_port(tenant):
    client = Client()
    client_id = register(client, ["http://127.0.0.1:1111/callback"]).json()["client_id"]
    _, challenge = pkce()
    sign_in(client, tenant)
    params = authorize_params(client_id, challenge, redirect="http://127.0.0.1:2222/callback")
    _, r = consent(client, params)
    assert r.status_code == 302 and r["Location"].startswith("http://127.0.0.1:2222/callback?")


def test_authorize_rejects_a_redirect_outside_the_policy(tenant):
    """Even an Application row registered by hand cannot send codes elsewhere."""
    app = get_application_model().objects.create(
        name="hand-made", client_type="public", authorization_grant_type="authorization-code",
        redirect_uris="https://evil.example/cb",
    )
    client = Client()
    sign_in(client, tenant)
    _, challenge = pkce()
    r = client.get(f"/oauth/authorize/?{urlencode(authorize_params(app.client_id, challenge, redirect='https://evil.example/cb'))}")
    assert r.status_code == 400 or "evil.example" not in r.get("Location", "")
    assert "code=" not in r.get("Location", "")


def test_authorize_rejects_another_resource(tenant):
    client = Client()
    client_id = register(client, [LOOPBACK]).json()["client_id"]
    sign_in(client, tenant)
    _, challenge = pkce()
    r = client.get(f"/oauth/authorize/?{urlencode(authorize_params(client_id, challenge, resource='https://other.example/mcp'))}")
    assert r.status_code == 400 and b"not Case Intel" in r.content
    assert "code=" not in r.get("Location", "")


# ---------------------------------------------------------------------------
# Sign-in, consent, code + PKCE, refresh
# ---------------------------------------------------------------------------


def test_authorize_without_session_redirects_to_sign_in():
    client = Client()
    client_id = register(client, [LOOPBACK]).json()["client_id"]
    _, challenge = pkce()
    r = client.get(f"/oauth/authorize/?{urlencode(authorize_params(client_id, challenge))}")
    assert r.status_code == 302 and r["Location"].startswith("/oauth/login/?next=")


def test_sign_in_page_is_plain_accessible_html():
    page = Client().get("/oauth/login/").content.decode()
    assert '<label for="username">' in page and '<label for="password">' in page
    assert 'autocomplete="current-password"' in page and 'lang="en"' in page


def test_sign_in_only_continues_to_the_authorize_endpoint(tenant):
    r = sign_in(Client(), tenant, next_url="https://evil.example/")
    assert r.status_code == 200  # signed-in page, no redirect


def test_sign_in_throttles_after_five_failures(tenant):
    client = Client()
    for _ in range(5):
        assert client.post("/oauth/login/", {"username": tenant.user.username, "password": "bad"}).status_code == 400
    assert sign_in(client, tenant).status_code == 429


def test_inactive_user_cannot_sign_in(tenant):
    tenant.user.is_active = False
    tenant.user.save()
    assert sign_in(Client(), tenant).status_code == 400


def test_consent_page_shows_redirect_host_and_scopes(tenant):
    client = Client()
    client_id = register(client, [CLAUDE_CALLBACK]).json()["client_id"]
    sign_in(client, tenant)
    _, challenge = pkce()
    page = client.get(f"/oauth/authorize/?{urlencode(authorize_params(client_id, challenge, redirect=CLAUDE_CALLBACK, scope='cases:read cases:write'))}")
    text = page.content.decode()
    assert "claude.ai" in text
    assert "Read your cases" in text and "Propose and confirm" in text
    assert "cannot send email" in text


def test_full_flow_issues_a_15_minute_audience_bound_token(tenant):
    client, client_id, tok = full_flow(tenant)
    assert tok.status_code == 200, tok.content
    body = tok.json()
    assert body["expires_in"] == 900 and body["token_type"] == "Bearer" and body["refresh_token"]
    row = get_access_token_model().objects.get(user=tenant.user, application__client_id=client_id)
    assert row.resource == [RESOURCE]
    assert row.token == ""  # hashed at rest (COMPLIANT_BCP_RFC9700_TOKEN_STORAGE)


def test_authorization_response_carries_iss(tenant):
    client = Client()
    client_id = register(client, [LOOPBACK]).json()["client_id"]
    sign_in(client, tenant)
    _, challenge = pkce()
    _, r = consent(client, authorize_params(client_id, challenge))
    assert parse_qs(urlsplit(r["Location"]).query)["iss"] == [ISSUER]


def test_code_exchange_needs_the_right_verifier(tenant):
    client = Client()
    client_id = register(client, [LOOPBACK]).json()["client_id"]
    sign_in(client, tenant)
    _, challenge = pkce()
    _, r = consent(client, authorize_params(client_id, challenge))
    code = parse_qs(urlsplit(r["Location"]).query)["code"][0]
    bad = client.post("/oauth/token/", {"grant_type": "authorization_code", "code": code, "redirect_uri": LOOPBACK,
                                        "client_id": client_id, "code_verifier": "wrong" * 10})
    assert bad.status_code == 400


def test_plain_pkce_is_rejected(tenant):
    client = Client()
    client_id = register(client, [LOOPBACK]).json()["client_id"]
    sign_in(client, tenant)
    params = authorize_params(client_id, "x" * 43)
    params["code_challenge_method"] = "plain"
    r = client.get(f"/oauth/authorize/?{urlencode(params)}")
    assert "code=" not in r.get("Location", "")


def test_refresh_rotates_and_reuse_is_invalid_grant(tenant):
    client, client_id, tok = full_flow(tenant)
    first = tok.json()["refresh_token"]
    r1 = client.post("/oauth/token/", {"grant_type": "refresh_token", "refresh_token": first, "client_id": client_id})
    assert r1.status_code == 200 and r1.json()["refresh_token"] != first
    r2 = client.post("/oauth/token/", {"grant_type": "refresh_token", "refresh_token": first, "client_id": client_id})
    assert r2.status_code == 400 and r2.json()["error"] == "invalid_grant"
    # The rotated family is revoked too.
    assert not get_access_token_model().objects.filter(user=tenant.user).exists()


# ---------------------------------------------------------------------------
# Connected apps (Settings API) and revocation
# ---------------------------------------------------------------------------


def test_connected_apps_lists_only_the_callers_apps(tenant):
    other = make_tenant("oauth_b", "Suresh")
    mint_token(tenant.user)
    mint_token(other.user)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {token_for(tenant.user)}")
    rows = api.get("/api/oauth/connected-apps/").json()["results"]
    assert len(rows) == 1 and rows[0]["scopes"] == ["cases:read", "cases:write"]


def test_revoke_ends_access_and_other_users_cannot_revoke(tenant):
    other = make_tenant("oauth_b", "Suresh")
    raw, row = mint_token(tenant.user)
    app_id = row.application_id
    api_b = APIClient()
    api_b.credentials(HTTP_AUTHORIZATION=f"Token {token_for(other.user)}")
    assert api_b.delete(f"/api/oauth/connected-apps/{app_id}/").status_code == 404
    assert get_access_token_model().objects.filter(pk=row.pk).exists()

    api_a = APIClient()
    api_a.credentials(HTTP_AUTHORIZATION=f"Token {token_for(tenant.user)}")
    assert api_a.delete(f"/api/oauth/connected-apps/{app_id}/").status_code == 204
    assert not get_access_token_model().objects.filter(user=tenant.user).exists()
    assert api_a.get("/api/oauth/connected-apps/").json()["results"] == []


def test_connected_apps_needs_a_signed_in_user():
    assert APIClient().get("/api/oauth/connected-apps/").status_code == 401


def test_password_change_revokes_oauth_tokens(tenant):
    client, client_id, tok = full_flow(tenant)
    assert get_refresh_token_model().objects.filter(user=tenant.user, revoked__isnull=True).exists()
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {token_for(tenant.user)}")
    r = api.post("/api/auth/change-password/", {"current_password": tenant.password,
                                                "new_password": "N3w-" + secrets.token_hex(10)}, format="json")
    assert r.status_code == 200, r.content
    assert not get_access_token_model().objects.filter(user=tenant.user).exists()
    assert not get_refresh_token_model().objects.filter(user=tenant.user, revoked__isnull=True).exists()
