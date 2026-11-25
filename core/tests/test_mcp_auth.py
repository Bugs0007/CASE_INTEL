"""The MCP endpoint over real HTTP (the ASGI app in-process, no network).

transaction=True: the token check and the tools run in worker threads with
their own DB connections, which only see committed rows.
"""

import json
from datetime import timedelta

import pytest
from django.utils import timezone
from starlette.testclient import TestClient

from core.services.auth_sessions import create_session
from core.tests.mcp_support import (  # noqa: F401 -- fixtures
    ISSUER,
    RESOURCE,
    _mcp_settings,
    _stub_search_embeddings,
    make_tenant,
    mint_token,
)

pytestmark = pytest.mark.django_db(transaction=True)

HOST = "http://api.caseintel.test"
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(method, params=None, id_=1):
    body = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        body["params"] = params
    return body


@pytest.fixture
def client():
    from mcp_server.app import Gate, build_server

    with TestClient(Gate(build_server().streamable_http_app()), base_url=HOST) as c:
        yield c


@pytest.fixture
def tenant():
    return make_tenant("auth_a", "Ramesh")


def post(client, token=None, body=None, headers=None, path="/mcp"):
    h = dict(HEADERS)
    if token:
        h["Authorization"] = f"Bearer {token}"
    h.update(headers or {})
    return client.post(path, headers=h, content=json.dumps(body or rpc("tools/list")))


def test_no_token_is_401_with_resource_metadata(client):
    r = post(client)
    assert r.status_code == 401
    www = r.headers["www-authenticate"]
    assert www.startswith("Bearer ")
    assert 'resource_metadata="https://api.caseintel.test/.well-known/oauth-protected-resource/mcp"' in www
    assert 'scope="cases:read"' in www


def test_protected_resource_metadata(client):
    r = client.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    assert r.json() == {
        "resource": RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": ["cases:read", "cases:write"],
        "bearer_methods_supported": ["header"],
        "resource_name": "Case Intel",
    }


def test_good_token_lists_and_calls_tools(client, tenant):
    raw, _ = mint_token(tenant.user)
    r = post(client, raw)
    assert r.status_code == 200, r.text
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert "get_case" in names and len(names) >= 11
    r = post(client, raw, rpc("tools/call", {"name": "get_case", "arguments": {"case_id": tenant.case.id}}))
    result = r.json()["result"]
    assert result["isError"] is False and result["structuredContent"]["case_id"] == tenant.case.id


def test_other_tenants_case_over_http_is_not_found(client, tenant):
    other = make_tenant("auth_b", "Suresh")
    raw, _ = mint_token(tenant.user)
    r = post(client, raw, rpc("tools/call", {"name": "get_case", "arguments": {"case_id": other.case.id}}))
    assert r.json()["result"]["structuredContent"]["error"] == "not_found"


def test_expired_token_is_401(client, tenant):
    raw, _ = mint_token(tenant.user, expires_in=-5)
    assert post(client, raw).status_code == 401


def test_revoked_token_is_401(client, tenant):
    raw, row = mint_token(tenant.user)
    row.revoke()
    assert post(client, raw).status_code == 401


def test_wrong_audience_is_401(client, tenant):
    raw, _ = mint_token(tenant.user, resource=("https://other.example/mcp",))
    assert post(client, raw).status_code == 401


def test_token_with_no_resource_is_401(client, tenant):
    """DOT treats an empty resource list as unrestricted; this server does not."""
    raw, _ = mint_token(tenant.user, resource=())
    assert post(client, raw).status_code == 401


def test_token_with_ours_and_another_resource_is_401(client, tenant):
    raw, _ = mint_token(tenant.user, resource=(RESOURCE, "https://other.example/mcp"))
    assert post(client, raw).status_code == 401


def test_inactive_user_is_401(client, tenant):
    raw, _ = mint_token(tenant.user)
    tenant.user.is_active = False
    tenant.user.save()
    assert post(client, raw).status_code == 401


def test_missing_read_scope_is_403_insufficient_scope(client, tenant):
    raw, _ = mint_token(tenant.user, scope="cases:write")
    r = post(client, raw)
    assert r.status_code == 403
    assert 'error="insufficient_scope"' in r.headers["www-authenticate"]


def test_token_in_query_string_is_rejected(client, tenant):
    raw, _ = mint_token(tenant.user)
    r = client.post(f"/mcp?access_token={raw}", headers=HEADERS, content=json.dumps(rpc("tools/list")))
    assert r.status_code == 400


def test_rest_session_token_is_not_accepted_on_mcp(client, tenant):
    _session, key = create_session(tenant.user)
    assert post(client, key).status_code == 401
    r = post(client, headers={"Authorization": f"Token {key}"})
    assert r.status_code == 401


def test_oauth_token_is_not_accepted_on_the_rest_api(tenant):
    from rest_framework.test import APIClient

    raw, _ = mint_token(tenant.user)
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {raw}")
    assert api.get("/api/cases/").status_code == 401
    api.credentials(HTTP_AUTHORIZATION=f"Token {raw}")
    assert api.get("/api/cases/").status_code == 401


def test_kill_switch_answers_503(client, tenant, settings):
    settings.MCP_ENABLED = False
    raw, _ = mint_token(tenant.user)
    assert post(client, raw).status_code == 503
    assert client.get("/.well-known/oauth-protected-resource/mcp").status_code == 503


def test_unknown_host_is_rejected(client, tenant):
    raw, _ = mint_token(tenant.user)
    assert post(client, raw, headers={"Host": "evil.example"}).status_code == 421


def test_unknown_browser_origin_is_rejected(client, tenant):
    raw, _ = mint_token(tenant.user)
    assert post(client, raw, headers={"Origin": "https://evil.example"}).status_code == 403
    assert post(client, raw, headers={"Origin": "https://claude.ai"}).status_code == 200


def test_body_over_64kb_is_rejected(client, tenant):
    raw, _ = mint_token(tenant.user)
    big = rpc("tools/call", {"name": "list_cases", "arguments": {"query": "x" * 70_000}})
    assert post(client, raw, big).status_code == 413


def test_token_expiring_mid_session_stops_working(client, tenant):
    raw, row = mint_token(tenant.user)
    assert post(client, raw).status_code == 200
    type(row).objects.filter(pk=row.pk).update(expires=timezone.now() - timedelta(seconds=1))
    assert post(client, raw).status_code == 401
