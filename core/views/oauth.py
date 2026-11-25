"""OAuth pages and APIs for the MCP connector (docs/MCP_PLAN.md section 4).

Two kinds of view live here:

1. Plain Django pages on the API host, used only inside an OAuth flow:
   SignInView (username + password, Django session cookie), SignOutView and
   ConsentView (DOT's AuthorizationView with Case Intel's template). The
   frontend's token login is not involved: it cannot set a cookie here.

2. Token-authenticated API views for Settings: list the apps connected to
   the caller's account, revoke one, and (Phase 2) the caller's recent MCP
   activity. Every query filters by request.user.

The sign-in page needs a design reference (docs/MCP_PLAN.md open question 2);
until then it is a plain, accessible page.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.db.models import Max, Min
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from oauth2_provider.models import get_access_token_model, get_application_model, get_refresh_token_model
from oauth2_provider.views import AuthorizationView
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import ActivityLog
from core.services import auth_sessions
from core.services.oauth_policy import resource_is_ours, revoke_user_grants

logger = logging.getLogger(__name__)

# Failed sign-ins allowed per username and per IP before a 15-minute wait.
# LocMemCache is per process: with N gunicorn workers the real ceiling is
# N times this. Good enough to stop a password-guessing script; see the
# CACHES comment in settings.py.
SIGN_IN_MAX_FAILURES = 5
SIGN_IN_WINDOW_SECONDS = 15 * 60
# The OAuth session only has to last through one consent screen.
SIGN_IN_SESSION_SECONDS = 15 * 60

AUTHORIZE_PATH = "/oauth/authorize/"


def _failure_keys(username: str, ip: str | None) -> list[str]:
    keys = [f"oauth-signin-fail:user:{(username or '').strip().lower()}"]
    if ip:
        keys.append(f"oauth-signin-fail:ip:{ip}")
    return keys


def _is_throttled(keys: list[str]) -> bool:
    return any((cache.get(key) or 0) >= SIGN_IN_MAX_FAILURES for key in keys)


def _record_failure(keys: list[str]) -> None:
    for key in keys:
        cache.add(key, 0, SIGN_IN_WINDOW_SECONDS)
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, SIGN_IN_WINDOW_SECONDS)


def _safe_next(request, value: str | None) -> str:
    """Only ever continue to the authorize endpoint on this host."""
    if (
        value
        and value.startswith(AUTHORIZE_PATH)
        and url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}, require_https=False)
    ):
        return value
    return ""


@method_decorator([never_cache, csrf_protect], name="dispatch")
class SignInView(View):
    template_name = "oauth/sign_in.html"

    def get(self, request):
        next_url = _safe_next(request, request.GET.get("next"))
        return render(request, self.template_name, {"next": next_url, "error": None, "username": ""})

    def post(self, request):
        next_url = _safe_next(request, request.POST.get("next"))
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        keys = _failure_keys(username, auth_sessions.client_ip(request.META))

        def fail(message, code=400):
            return render(
                request,
                self.template_name,
                {"next": next_url, "error": message, "username": username},
                status=code,
            )

        if _is_throttled(keys):
            return fail("Too many failed attempts. Wait 15 minutes, then try again.", code=429)
        user = authenticate(request, username=username, password=password) if username and password else None
        if user is None or not user.is_active:
            _record_failure(keys)
            return fail("The username or password is not correct.")
        for key in keys:
            cache.delete(key)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session.set_expiry(SIGN_IN_SESSION_SECONDS)
        if next_url:
            return redirect(next_url)
        return render(request, "oauth/signed_in.html", {})


@method_decorator([never_cache, csrf_protect], name="dispatch")
class SignOutView(View):
    def post(self, request):
        logout(request)
        return render(request, "oauth/signed_in.html", {"signed_out": True})


class ConsentView(AuthorizationView):
    """DOT's authorize endpoint with Case Intel's consent page.

    Adds the redirect host (so the user sees where the code goes) and a
    plain note on where the data goes. DOT still validates everything:
    client, redirect URI (plus oauth_policy's allow-list), PKCE S256,
    scopes, and the `resource` audience.
    """

    template_name = "oauth2_provider/authorize.html"

    def dispatch(self, request, *args, **kwargs):
        # RFC 8707: refuse a foreign `resource` before showing consent (DOT
        # itself only checks it when the code is issued and exchanged).
        values = request.GET.getlist("resource") + request.POST.getlist("resource")
        requested = [part for value in values for part in value.split()]
        if any(not resource_is_ours(value) for value in requested):
            return render(
                request,
                self.template_name,
                {"error": {"error": "invalid_target",
                           "description": "This app asked for access to a server that is not Case Intel."}},
                status=400,
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        redirect_uri = context.get("redirect_uri") or ""
        parts = urlsplit(redirect_uri)
        context["redirect_host"] = parts.hostname or ""
        context["redirect_is_loopback"] = parts.hostname in settings.OAUTH_LOOPBACK_HOSTS
        context["signed_in_as"] = getattr(self.request.user, "username", "")
        return context


# ---------------------------------------------------------------------------
# Settings API: connected apps (and Phase 2: recent activity)
# ---------------------------------------------------------------------------


def _client_label(application) -> str:
    """A human name for an OAuth client. A CIMD client_id is an https URL;
    show its host rather than the whole URL."""
    if application.name:
        return application.name
    parts = urlsplit(application.client_id)
    return parts.hostname or "Unnamed app"


def connected_applications(user) -> list[dict]:
    """The applications holding a live refresh or access token for `user`."""
    Application = get_application_model()
    AccessToken = get_access_token_model()
    RefreshToken = get_refresh_token_model()

    refresh = (
        RefreshToken.objects.filter(user=user, revoked__isnull=True)
        .values("application_id")
        .annotate(first=Min("created"), last=Max("updated"))
    )
    access = (
        AccessToken.objects.filter(user=user)
        .values("application_id")
        .annotate(first=Min("created"), last=Max("updated"))
    )
    seen: dict[int, dict] = {}
    for row in list(refresh) + list(access):
        slot = seen.setdefault(row["application_id"], {"first": row["first"], "last": row["last"]})
        slot["first"] = min(slot["first"], row["first"])
        slot["last"] = max(slot["last"], row["last"])

    scopes: dict[int, set] = {}
    for app_id, scope in AccessToken.objects.filter(user=user).values_list("application_id", "scope"):
        scopes.setdefault(app_id, set()).update((scope or "").split())
    for app_id, scope in RefreshToken.objects.filter(user=user, revoked__isnull=True).values_list(
        "application_id", "access_token__scope"
    ):
        scopes.setdefault(app_id, set()).update((scope or "").split())

    rows = []
    for application in Application.objects.filter(id__in=list(seen)).order_by("id"):
        window = seen[application.id]
        rows.append(
            {
                "id": application.id,
                "name": _client_label(application),
                "registration_source": application.registration_source,
                "scopes": sorted(scopes.get(application.id, set())),
                "connected_at": window["first"],
                "last_active_at": window["last"],
            }
        )
    return rows


class ConnectedAppListView(APIView):
    """GET /api/oauth/connected-apps/ -- apps that can reach this account
    through the MCP connector."""

    def get(self, request):
        return Response({"results": connected_applications(request.user)})


MCP_ACTIVITY_TYPES = ("mcp_call", "mcp_write")
ACTIVITY_ROWS = 50


class McpActivityView(APIView):
    """GET /api/oauth/activity/ -- the caller's last MCP tool calls, newest
    first, from their own audit rows. Only fixed fields leave: tool, result,
    kind, case, app; never the stored args."""

    def get(self, request):
        logs = (
            ActivityLog.objects.filter(owner=request.user, activity_type__in=MCP_ACTIVITY_TYPES)
            .select_related("case")
            .order_by("-created_at", "-id")[:ACTIVITY_ROWS]
        )
        app_names = {
            app.client_id: _client_label(app)
            for app in get_application_model().objects.filter(
                id__in=[row["id"] for row in connected_applications(request.user)]
            )
        }
        results = []
        for log in logs:
            try:
                payload = json.loads(log.description or "{}")
            except ValueError:
                payload = {}
            case_ok = log.case_id is not None and log.case is not None and log.case.owner_id == request.user.id
            results.append(
                {
                    "id": log.id,
                    "created_at": log.created_at,
                    "kind": "write" if log.activity_type == "mcp_write" else "read",
                    "tool": str(payload.get("tool") or "")[:50],
                    "result": str(payload.get("result") or "")[:20],
                    "case_id": log.case_id if case_ok else None,
                    "case_title": log.case.title if case_ok else None,
                    "app_name": app_names.get(payload.get("client_id")),
                    "proposal_id": payload.get("proposal_id") if isinstance(payload.get("proposal_id"), int) else None,
                }
            )
        return Response({"results": results})


class ConnectedAppRevokeView(APIView):
    """DELETE /api/oauth/connected-apps/<id>/ -- end that app's access to
    this account at once (refresh and access tokens). 404 when the app holds
    nothing for this user, so another user's connections never show."""

    def delete(self, request, pk):
        if not any(row["id"] == pk for row in connected_applications(request.user)):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        application = get_application_model().objects.get(pk=pk)
        ended = revoke_user_grants(request.user, application=application)
        ActivityLog.objects.create(
            owner=request.user,
            activity_type="mcp_revoke",
            description=f'{{"application_id": {pk}, "tokens_ended": {ended}}}',
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
