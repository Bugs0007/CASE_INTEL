"""MCP read tools: tenant isolation, untrusted text, caps, limits, audit,
and parity with the services they mirror (docs/MCP_PLAN.md sections 5-7)."""

import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from core.models import (
    ActivityLog,
    AppearanceFee,
    Case,
    CaseEvent,
    CaseNote,
    ClientMessage,
    CourtOrder,
    Document,
    DocumentChunk,
    Hearing,
    Task,
)
from core.tests.mcp_support import (  # noqa: F401 -- fixtures
    ID_TOOL_ARGS,
    INJECTION,
    READ_TOOL_ARGS,
    _mcp_settings,
    _stub_search_embeddings,
    call,
    ctx_for,
    make_tenant,
)
from mcp_server.safety import MAX_TEXT_CHARS, UNTRUSTED_NOTICE

pytestmark = pytest.mark.django_db

CASE_DATA_MODELS = (Case, Hearing, Task, CaseEvent, CaseNote, CourtOrder, Document, DocumentChunk, ClientMessage,
                    AppearanceFee)


@pytest.fixture
def a():
    return make_tenant("mcp_a", "Ramesh")


@pytest.fixture
def b():
    return make_tenant("mcp_b", "Suresh")


def data(result):
    assert not result.isError, result.content[0].text
    return result.structuredContent


def _walk(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    else:
        yield value


def _ids(payload, key):
    found = set()

    def visit(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == key and isinstance(v, int):
                    found.add(v)
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(payload)
    return found


# ---------------------------------------------------------------------------
# Every tool works for its owner
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(READ_TOOL_ARGS))
def test_read_tool_returns_the_callers_data(a, b, name):
    out = data(call(ctx_for(a.user), name, **READ_TOOL_ARGS[name](a)))
    assert "truncated" in out and "as_of" in out
    assert b.case.id not in _ids(out, "case_id")


def test_schedule_carries_cause_list_slot(a):
    items = data(call(ctx_for(a.user), "get_schedule"))["items"]
    hearing = next(i for i in items if i["type"] == "hearing")
    assert hearing["cause_list_status"] == "listed" and hearing["item_number"] == "12"
    assert hearing["cause_list_checked_at"]


def test_last_order_frames_directions_from_the_callers_side(a):
    summary = data(call(ctx_for(a.user), "get_last_order", case_id=a.case.id))["summary"]
    assert summary["party_role"] == "petitioner"
    assert summary["your_side_directions"][0]["untrusted_text"].startswith("File rejoinder")
    assert summary["other_side_directions"][0]["untrusted_text"] == "File counter"


def test_hearing_prep_returns_cached_briefing_without_generating(a):
    with patch("core.services.llm_client.LLMClient", side_effect=AssertionError("LLM called")):
        out = data(call(ctx_for(a.user), "get_hearing_prep", hearing_id=a.hearing.id))
    assert out["briefing"]["state"] == "cached"
    assert out["last_order"]["order_id"] == a.order.id
    assert out["cause_list"]["matches"][0]["is_primary"] is True


# ---------------------------------------------------------------------------
# Tenant isolation: A with B's ids gets "not found", never B's rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(ID_TOOL_ARGS))
def test_other_tenants_id_is_not_found_exactly_like_a_missing_id(a, b, name):
    ctx = ctx_for(a.user)
    theirs = call(ctx, name, **ID_TOOL_ARGS[name](b))
    assert theirs.isError and theirs.structuredContent["error"] == "not_found"
    missing_args = {k: (999_999 if k.endswith("_id") else v) for k, v in ID_TOOL_ARGS[name](b).items()}
    missing = call(ctx, name, **missing_args)
    assert missing.structuredContent == theirs.structuredContent  # no existence leak


@pytest.mark.parametrize("name", ["get_schedule", "list_cases", "list_tasks", "list_client_drafts", "list_unpaid_fees"])
def test_list_tools_never_return_other_tenants_rows(a, b, name):
    out = data(call(ctx_for(a.user), name))
    assert b.case.id not in _ids(out, "case_id")
    blob = json.dumps(out)
    assert "Suresh" not in blob


def test_list_cases_query_matching_only_other_tenant_returns_nothing(a, b):
    out = data(call(ctx_for(a.user), "list_cases", query="Suresh"))
    assert out["cases"] == [] and out["total"] == 0


@pytest.mark.parametrize("with_case", [True, False])
def test_search_documents_is_owner_scoped_with_and_without_case_id(a, b, with_case):
    args = {"query": "settlement amount lakh"}
    if with_case:
        args["case_id"] = a.case.id
    out = data(call(ctx_for(a.user), "search_case_documents", **args))
    assert {s["document_id"] for s in out["snippets"]} == {a.document.id}
    assert "Suresh" not in json.dumps(out)


def test_search_with_other_tenants_case_id_is_not_found(a, b):
    result = call(ctx_for(a.user), "search_case_documents", query="settlement", case_id=b.case.id)
    assert result.structuredContent["error"] == "not_found"


def test_inactive_user_context_cannot_be_built(a):
    from mcp_server.access import AccessDenied, build_context

    a.user.is_active = False
    a.user.save()
    with pytest.raises(AccessDenied):
        build_context(user_id=a.user.id, scopes=["cases:read"], client_id="c", token_id=1)


# ---------------------------------------------------------------------------
# Read tools write nothing
# ---------------------------------------------------------------------------


def test_read_tools_write_no_case_data(a, b):
    before = {m.__name__: m.objects.count() for m in CASE_DATA_MODELS}
    ctx = ctx_for(a.user)
    for name, args in READ_TOOL_ARGS.items():
        data(call(ctx, name, **args(a)))
    after = {m.__name__: m.objects.count() for m in CASE_DATA_MODELS}
    assert before == after


# ---------------------------------------------------------------------------
# Untrusted text and prompt injection
# ---------------------------------------------------------------------------


def test_injected_court_text_is_cleaned_labelled_and_does_not_change_shape(a):
    bad = make_tenant("mcp_injected", "Kiran", injected=True)
    for name, args in READ_TOOL_ARGS.items():
        clean_out = call(ctx_for(a.user), name, **args(a))
        dirty_out = call(ctx_for(bad.user), name, **args(bad))
        assert not dirty_out.isError, name
        assert set(dirty_out.structuredContent) == set(clean_out.structuredContent), name
        text = dirty_out.content[0].text
        for ch in ("​", "‮", "\x07", "<script>"):
            assert ch not in text, (name, repr(ch))
        if "IGNORE ALL PREVIOUS INSTRUCTIONS" in text:
            assert text.startswith(UNTRUSTED_NOTICE), name


def test_free_court_text_only_leaves_in_untrusted_text_fields(a):
    bad = make_tenant("mcp_injected2", "Kiran", injected=True)
    out = data(call(ctx_for(bad.user), "get_last_order", case_id=bad.case.id))
    summary = out["summary"]
    assert "IGNORE ALL" in summary["what_happened"]["untrusted_text"]
    for key in ("status", "route", "party_role", "next_date"):
        assert "IGNORE" not in json.dumps(summary[key])


def test_injection_cannot_cause_a_write(a):
    bad = make_tenant("mcp_injected3", "Kiran", injected=True)
    before = {m.__name__: m.objects.count() for m in CASE_DATA_MODELS}
    for name, args in READ_TOOL_ARGS.items():
        call(ctx_for(bad.user), name, **args(bad))
    assert before == {m.__name__: m.objects.count() for m in CASE_DATA_MODELS}


def test_clean_text_strips_controls_invisibles_and_tags():
    from mcp_server.safety import clean_text

    assert clean_text("a​b‮c<b>d</b>\x00e\nf") == "abc d e\nf"


# ---------------------------------------------------------------------------
# Size caps
# ---------------------------------------------------------------------------


def test_free_text_is_capped_per_call(a):
    CourtOrder.objects.filter(pk=a.order.pk).update(
        summary_what_happened="x" * 50_000,
        summary_petitioner_directions=["y" * 5_000] * 30,
    )
    out = data(call(ctx_for(a.user), "get_last_order", case_id=a.case.id))
    total = sum(len(v) for v in _walk(out) if isinstance(v, str) and set(v) <= {"x", "y", "…"})
    assert total <= MAX_TEXT_CHARS + 50
    assert out["truncated"] is True


def test_rows_are_capped_at_50(a):
    Task.objects.bulk_create(
        [Task(owner=a.user, case=a.case, title=f"t{i}", due_date=date.today()) for i in range(70)]
    )
    out = data(call(ctx_for(a.user), "list_tasks", limit=500))
    assert len(out["tasks"]) == 50 and out["truncated"] is True and out["total"] == 71


def test_schedule_window_is_limited_to_31_days(a):
    result = call(ctx_for(a.user), "get_schedule", date_from="2026-01-01", date_to="2026-03-01")
    assert result.structuredContent["error"] == "invalid_input"


# ---------------------------------------------------------------------------
# Scope, errors, rate limits
# ---------------------------------------------------------------------------


def test_tool_needs_its_scope(a):
    result = call(ctx_for(a.user, scopes=("cases:write",)), "list_cases")
    assert result.structuredContent["error"] == "insufficient_scope"


def test_internal_errors_never_return_raw_text(a):
    with patch(
        "core.services.practice_assistant.reads.calendar_window",
        side_effect=RuntimeError("SELECT secret FROM core_case"),
    ):
        result = call(ctx_for(a.user), "get_schedule")
    assert result.structuredContent == {"error": "internal_error", "message": "The tool failed. Try again later."}
    assert "secret" not in result.content[0].text


def test_per_minute_limit(a, settings):
    settings.MCP_RATE_PER_MINUTE = 3
    ctx = ctx_for(a.user)
    for _ in range(3):
        data(call(ctx, "list_cases"))
    assert call(ctx, "list_cases").structuredContent["error"] == "rate_limited"


def test_search_has_its_own_tighter_limit(a, settings):
    settings.MCP_RATE_SEARCH_PER_MINUTE = 2
    ctx = ctx_for(a.user)
    for _ in range(2):
        data(call(ctx, "search_case_documents", query="settlement", case_id=a.case.id))
    limited = call(ctx, "search_case_documents", query="settlement", case_id=a.case.id)
    assert limited.structuredContent["error"] == "rate_limited"
    data(call(ctx, "list_cases"))  # other tools still run


def test_daily_limit_counts_audit_rows(a, settings):
    settings.MCP_RATE_PER_DAY = 5
    ActivityLog.objects.bulk_create([ActivityLog(owner=a.user, activity_type="mcp_call") for _ in range(5)])
    assert call(ctx_for(a.user), "list_cases").structuredContent["error"] == "rate_limited"


def test_limits_are_per_user(a, b, settings):
    settings.MCP_RATE_PER_MINUTE = 1
    data(call(ctx_for(a.user), "list_cases"))
    data(call(ctx_for(b.user), "list_cases"))


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_every_call_writes_one_audit_row_without_document_text(a):
    ctx = ctx_for(a.user, client_id="claude-test", token_id=77)
    for name, args in READ_TOOL_ARGS.items():
        before = ActivityLog.objects.filter(owner=a.user, activity_type="mcp_call").count()
        call(ctx, name, **args(a))
        rows = ActivityLog.objects.filter(owner=a.user, activity_type="mcp_call").order_by("-id")
        assert rows.count() == before + 1, name
        payload = json.loads(rows.first().description)
        assert payload["tool"] == name and payload["result"] == "ok" and payload["token_id"] == 77
        assert payload["client_id"] == "claude-test" and "duration_ms" in payload
        blob = rows.first().description
        assert "settlement" not in blob and "lakh" not in blob and "Notice issued" not in blob


def test_audit_row_records_denials_and_errors(a):
    call(ctx_for(a.user, scopes=()), "list_cases")
    last = ActivityLog.objects.filter(owner=a.user).latest("id")
    assert json.loads(last.description)["result"] == "denied"


def test_audit_failure_does_not_fail_the_call(a):
    with patch("mcp_server.audit.ActivityLog.objects.create", side_effect=RuntimeError("db down")):
        data(call(ctx_for(a.user), "list_cases"))


# ---------------------------------------------------------------------------
# Parity with the services this process may not import
# ---------------------------------------------------------------------------


def test_order_summary_matches_build_order_summary(a):
    from core.serializers.order_summary import build_order_summary
    from mcp_server.safety import TextBudget
    from mcp_server.tools.orders import render_order_summary

    order = CourtOrder.objects.select_related("case").get(pk=a.order.pk)
    ours = render_order_summary(order, TextBudget())
    theirs = build_order_summary(order)

    from mcp_server.safety import clean_text

    def unwrap(value):
        if isinstance(value, dict) and "untrusted_text" in value:
            return value["untrusted_text"]
        if isinstance(value, list):
            return [unwrap(v) for v in value]
        return value

    def cleaned(value):
        if isinstance(value, str):
            return clean_text(value)
        if isinstance(value, list):
            return [clean_text(v) for v in value]
        return value

    for key in ("status", "what_happened", "your_side_directions", "other_side_directions", "party_role",
                "next_date_purpose", "is_routine_adjournment"):
        assert unwrap(ours[key]) == cleaned(theirs[key]), key
    # Role known: each direction appears once, under your side / the other side.
    assert ours["petitioner_directions"] is None and ours["respondent_directions"] is None
    assert ours["next_date"] == theirs["next_date"].isoformat()

    Case.objects.filter(pk=a.case.pk).update(user_party_role="unknown")
    order = CourtOrder.objects.select_related("case").get(pk=a.order.pk)
    ours, theirs = render_order_summary(order, TextBudget()), build_order_summary(order)
    assert unwrap(ours["petitioner_directions"]) == cleaned(theirs["petitioner_directions"])
    assert unwrap(ours["respondent_directions"]) == cleaned(theirs["respondent_directions"])
    assert ours["your_side_directions"] is None and theirs["your_side_directions"] is None


def test_hearing_prep_matches_assemble_hearing_digest(a):
    from core.services.hearing_digest import assemble_hearing_digest
    from mcp_server.tools.hearings import RESOLVED_SUMMARY_STATUSES, compose_prep
    from core.services.hearing_digest import assemble as assemble_module

    assert RESOLVED_SUMMARY_STATUSES == assemble_module.RESOLVED_SUMMARY_STATUSES
    hearing = Hearing.objects.select_related("case").get(pk=a.hearing.pk)
    theirs = assemble_hearing_digest(hearing)
    ours = compose_prep(ctx_for(a.user), hearing)
    assert ours["last_order"] == theirs.last_order
    assert ours["open_tasks"] == theirs.open_tasks
    assert ours["documents"] == theirs.documents
    assert ours["purposes"] == theirs.purposes
    assert ours["snapshot"] == theirs.snapshot


def test_order_sync_state_matches_order_sync_summary(a):
    from core.services.order_sync_status import _STATE_BY_JOB_STATUS, order_sync_summary
    from mcp_server.tools.common import ORDER_SYNC_STATE_BY_JOB_STATUS, order_sync_state

    assert ORDER_SYNC_STATE_BY_JOB_STATUS == _STATE_BY_JOB_STATUS
    ours = order_sync_state(ctx_for(a.user), a.case)
    theirs = order_sync_summary(a.case)
    assert ours["state"] == theirs["state"]
    assert (ours["found"], ours["downloaded"]) == (theirs["found"], theirs["downloaded"])


def test_refresh_interval_matches_court_tracking():
    from core.services.court_tracking import MIN_REFETCH_INTERVAL
    from mcp_server.tools.common import MIN_REFETCH_INTERVAL as OURS

    assert OURS == MIN_REFETCH_INTERVAL


def test_freshness_reports_next_allowed_refresh(a):
    Case.objects.filter(pk=a.case.pk).update(last_fetched_at=timezone.now() - timedelta(minutes=10))
    out = data(call(ctx_for(a.user), "get_data_freshness", case_id=a.case.id))
    assert out["ecourts"]["next_refresh_allowed_at"] > out["ecourts"]["last_checked_at"]
