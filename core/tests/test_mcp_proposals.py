"""Phase 2 write tools: propose, then confirm (docs/MCP_PLAN.md section 5)."""

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
    ClientContact,
    ClientMessage,
    CourtOrder,
    Document,
    DocumentChunk,
    Hearing,
    McpProposal,
    SentMessage,
    Task,
)
from core.tests.mcp_support import (  # noqa: F401 -- fixtures
    INJECTION,
    READ_TOOL_ARGS,
    _mcp_settings,
    _stub_search_embeddings,
    call,
    ctx_for,
    make_tenant,
)

pytestmark = pytest.mark.django_db

CASE_DATA_MODELS = (Case, Hearing, Task, CaseEvent, CaseNote, CourtOrder, Document, DocumentChunk, ClientMessage,
                    AppearanceFee, SentMessage)


@pytest.fixture
def a():
    t = make_tenant("prop_a", "Ramesh")
    ClientContact.objects.create(owner=t.user, case=t.case, name="Ramesh", email="ramesh@example.com",
                                 receive_case_updates=True)
    return t


@pytest.fixture
def b():
    return make_tenant("prop_b", "Suresh")


def ok(result):
    assert not result.isError, result.content[0].text
    return result.structuredContent


def counts():
    return {m.__name__: m.objects.count() for m in CASE_DATA_MODELS}


def proposals(a):
    return {
        "propose_task": {"title": "File rejoinder", "case_id": a.case.id, "due_date": "2026-12-01"},
        "propose_case_note": {"case_id": a.case.id, "text": "Client called about the next date."},
        "propose_case_event": {"case_id": a.case.id, "date": "2026-12-02", "title": "Mediation",
                               "start_time": "10:00", "end_time": "11:30", "event_type": "mediation"},
        "propose_task_update": {"task_id": a.task.id, "status": "completed"},
        "propose_client_update_draft": {"case_id": a.case.id},
    }


# ---------------------------------------------------------------------------
# Propose writes nothing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(["propose_task", "propose_case_note", "propose_case_event",
                                         "propose_task_update", "propose_client_update_draft"]))
def test_propose_writes_only_the_proposal_row(a, name):
    before, before_p = counts(), McpProposal.objects.count()
    out = ok(call(ctx_for(a.user), name, **proposals(a)[name]))
    assert counts() == before
    assert McpProposal.objects.count() == before_p + 1
    assert out["proposal_id"] and out["preview"] and out["can_confirm"] is True
    assert "Nothing has changed yet" in out["next_step"]


def test_propose_needs_write_scope(a):
    result = call(ctx_for(a.user, scopes=("cases:read",)), "propose_task", title="x")
    assert result.structuredContent["error"] == "insufficient_scope"
    assert McpProposal.objects.count() == 0


# ---------------------------------------------------------------------------
# Confirm runs the real change, once
# ---------------------------------------------------------------------------


def test_confirm_task(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    out = ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    task = Task.objects.get(pk=out["result"]["task_id"])
    assert (task.owner, task.case, task.kind, task.due_date) == (a.user, a.case, Task.KIND_MANUAL, date(2026, 12, 1))


def test_confirm_case_note(a):
    pid = ok(call(ctx_for(a.user), "propose_case_note", **proposals(a)["propose_case_note"]))["proposal_id"]
    out = ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    note = CaseNote.objects.get(pk=out["result"]["note_id"])
    assert note.owner == a.user and note.body == "Client called about the next date."


def test_confirm_case_event_never_makes_a_hearing(a):
    hearings = Hearing.objects.count()
    pid = ok(call(ctx_for(a.user), "propose_case_event", **proposals(a)["propose_case_event"]))["proposal_id"]
    out = ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    event = CaseEvent.objects.get(pk=out["result"]["event_id"])
    assert event.event_type == "mediation" and str(event.start_time) == "10:00:00"
    assert Hearing.objects.count() == hearings


def test_confirm_task_update_marks_user_modified(a):
    pid = ok(call(ctx_for(a.user), "propose_task_update", **proposals(a)["propose_task_update"]))["proposal_id"]
    ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    a.task.refresh_from_db()
    assert a.task.status == Task.STATUS_COMPLETED and a.task.completed_at and a.task.user_modified


def test_confirm_client_update_only_saves_a_draft(a):
    sent = SentMessage.objects.count()
    with patch("django.core.mail.EmailMessage.send", side_effect=AssertionError("sent an email")):
        pid = ok(call(ctx_for(a.user), "propose_client_update_draft", case_id=a.case.id))["proposal_id"]
        out = ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    assert out["result"]["sent"] is False
    draft = ClientMessage.objects.get(pk=out["result"]["draft_id"])
    assert draft.status == ClientMessage.STATUS_DRAFT and draft.owner == a.user
    assert draft.recipients and draft.recipients[0]["email"] == "ramesh@example.com"
    assert SentMessage.objects.count() == sent


def test_client_update_without_contacts_is_blocked(b):
    out = ok(call(ctx_for(b.user), "propose_client_update_draft", case_id=b.case.id))
    assert out["can_confirm"] is False and out["blockers"]
    result = call(ctx_for(b.user), "confirm_proposal", proposal_id=out["proposal_id"])
    assert result.structuredContent["error"] == "invalid_input"


def test_double_confirm_is_idempotent(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    first = ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    tasks = Task.objects.count()
    second = ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    assert second["result"] == first["result"] and Task.objects.count() == tasks


def test_expired_proposal_cannot_be_confirmed(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    McpProposal.objects.filter(pk=pid).update(expires_at=timezone.now() - timedelta(seconds=1))
    tasks = Task.objects.count()
    result = call(ctx_for(a.user), "confirm_proposal", proposal_id=pid)
    assert result.structuredContent["error"] == "invalid_input" and "expired" in result.content[0].text
    assert McpProposal.objects.get(pk=pid).status == McpProposal.STATUS_EXPIRED
    assert Task.objects.count() == tasks


def test_changed_args_cannot_be_confirmed(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    proposal = McpProposal.objects.get(pk=pid)
    proposal.args = {**proposal.args, "title": "Something the user never saw"}
    proposal.save()
    tasks = Task.objects.count()
    result = call(ctx_for(a.user), "confirm_proposal", proposal_id=pid)
    assert result.structuredContent["error"] == "invalid_input" and "changed" in result.content[0].text
    assert Task.objects.count() == tasks


def test_cancelled_proposal_cannot_be_confirmed_and_cancel_is_idempotent(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    assert ok(call(ctx_for(a.user), "cancel_proposal", proposal_id=pid))["status"] == "cancelled"
    assert ok(call(ctx_for(a.user), "cancel_proposal", proposal_id=pid))["status"] == "cancelled"
    assert call(ctx_for(a.user), "confirm_proposal", proposal_id=pid).structuredContent["error"] == "invalid_input"


def test_confirmed_proposal_cannot_be_cancelled(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    assert call(ctx_for(a.user), "cancel_proposal", proposal_id=pid).structuredContent["error"] == "invalid_input"


def test_confirm_needs_write_scope(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    result = call(ctx_for(a.user, scopes=("cases:read",)), "confirm_proposal", proposal_id=pid)
    assert result.structuredContent["error"] == "insufficient_scope"
    assert McpProposal.objects.get(pk=pid).status == McpProposal.STATUS_OPEN


def test_confirm_has_its_own_rate_limit(a, settings):
    settings.MCP_RATE_CONFIRM_PER_MINUTE = 1
    ctx = ctx_for(a.user)
    p1 = ok(call(ctx, "propose_task", title="one"))["proposal_id"]
    p2 = ok(call(ctx, "propose_task", title="two"))["proposal_id"]
    ok(call(ctx, "confirm_proposal", proposal_id=p1))
    assert call(ctx, "confirm_proposal", proposal_id=p2).structuredContent["error"] == "rate_limited"


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


def test_other_user_cannot_confirm_or_cancel(a, b):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    tasks = Task.objects.count()
    assert call(ctx_for(b.user), "confirm_proposal", proposal_id=pid).structuredContent["error"] == "not_found"
    assert call(ctx_for(b.user), "cancel_proposal", proposal_id=pid).structuredContent["error"] == "not_found"
    assert Task.objects.count() == tasks
    assert McpProposal.objects.get(pk=pid).status == McpProposal.STATUS_OPEN


@pytest.mark.parametrize("name,args", [
    ("propose_task", lambda b: {"title": "x", "case_id": b.case.id}),
    ("propose_case_note", lambda b: {"case_id": b.case.id, "text": "x"}),
    ("propose_case_event", lambda b: {"case_id": b.case.id, "date": "2026-12-02", "title": "x"}),
    ("propose_task_update", lambda b: {"task_id": b.task.id, "status": "completed"}),
    ("propose_client_update_draft", lambda b: {"case_id": b.case.id}),
])
def test_cannot_propose_on_other_users_rows(a, b, name, args):
    result = call(ctx_for(a.user), name, **args(b))
    assert result.structuredContent["error"] == "not_found"
    assert McpProposal.objects.count() == 0


def test_confirm_rechecks_ownership_at_run_time(a, b):
    """A proposal whose case changed hands is refused, not run on the other tenant."""
    pid = ok(call(ctx_for(a.user), "propose_case_note", case_id=a.case.id, text="x"))["proposal_id"]
    Case.objects.filter(pk=a.case.pk).update(owner=b.user)
    notes = CaseNote.objects.count()
    assert call(ctx_for(a.user), "confirm_proposal", proposal_id=pid).structuredContent["error"] == "not_found"
    assert CaseNote.objects.count() == notes


# ---------------------------------------------------------------------------
# Validation and injection
# ---------------------------------------------------------------------------


def test_event_end_must_follow_start(a):
    result = call(ctx_for(a.user), "propose_case_event", case_id=a.case.id, date="2026-12-02", title="x",
                  start_time="11:00", end_time="10:00")
    assert result.structuredContent["error"] == "invalid_input"


def test_overlong_input_is_rejected(a):
    assert call(ctx_for(a.user), "propose_task", title="x" * 300).structuredContent["error"] == "invalid_input"


def test_preview_quotes_model_text_and_strips_controls(a):
    out = ok(call(ctx_for(a.user), "propose_task", title=INJECTION))
    assert "‮" not in out["preview"] and "<script>" not in out["preview"]
    assert out["preview"].startswith('Create a task "')


def test_injected_court_text_cannot_cause_a_write_without_a_proposal():
    """Reading every tool over injected court text, then trying to confirm
    an id the user never proposed, changes nothing."""
    bad = make_tenant("prop_injected", "Kiran", injected=True)
    before = counts()
    ctx = ctx_for(bad.user)
    for name, args in READ_TOOL_ARGS.items():
        call(ctx, name, **args(bad))
    for guess in (1, 2, 3, 999):
        assert call(ctx, "confirm_proposal", proposal_id=guess).isError
    assert counts() == before
    assert McpProposal.objects.count() == 0


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def test_confirm_writes_its_audit_row_in_the_same_transaction(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    ok(call(ctx_for(a.user), "confirm_proposal", proposal_id=pid))
    rows = [json.loads(r.description) for r in ActivityLog.objects.filter(owner=a.user, activity_type="mcp_write").order_by("id")]
    assert [r["tool"] for r in rows if r.get("proposal_id") == pid] == ["propose_task", "confirm_proposal"]
    assert all("File rejoinder" not in json.dumps(r) for r in rows)


def test_audit_failure_rolls_back_the_confirm(a):
    pid = ok(call(ctx_for(a.user), "propose_task", **proposals(a)["propose_task"]))["proposal_id"]
    tasks = Task.objects.count()
    with patch("mcp_server.tools.proposals.ActivityLog.save", side_effect=RuntimeError("audit down")):
        result = call(ctx_for(a.user), "confirm_proposal", proposal_id=pid)
    assert result.structuredContent["error"] == "internal_error"
    assert Task.objects.count() == tasks
    assert McpProposal.objects.get(pk=pid).status == McpProposal.STATUS_OPEN


# ---------------------------------------------------------------------------
# Settings API: recent Claude activity
# ---------------------------------------------------------------------------


def test_activity_api_lists_only_the_callers_mcp_rows(a, b):
    from rest_framework.test import APIClient

    from core.tests.auth_helpers import token_for

    ok(call(ctx_for(a.user), "list_cases"))
    ok(call(ctx_for(b.user), "list_cases"))
    ActivityLog.objects.create(owner=a.user, activity_type="note_added", description="not mcp")
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Token {token_for(a.user)}")
    rows = api.get("/api/oauth/activity/").json()["results"]
    assert len(rows) == 1 and rows[0]["tool"] == "list_cases" and rows[0]["kind"] == "read"
    assert rows[0]["result"] == "ok"
