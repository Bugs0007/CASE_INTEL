"""The case-assistant draft storage API: /api/case-assistant/drafts/...

No model is called here. Ready drafts are built by creating revision rows
directly with a body that passes the real schema validator.
"""
import copy

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from core.models import (
    AssistantDraft,
    AssistantDraftRevision,
    Case,
    Conversation,
    Document,
    Message,
    ProcessingJob,
)

pytestmark = pytest.mark.django_db

BASE = "/api/case-assistant/drafts/"
EVIDENCE = [
    {
        "id": "hearing:1",
        "kind": "hearing",
        "label": "Hearing on 12 Nov",
        "ref": {"kind": "hearing", "id": 1, "case_id": 1, "label": "Hearing", "recorded_at": None},
        "fingerprint": "abc",
    }
]


def body(subtype="status_memo", title="Status", evidence=("hearing:1",), text="Next hearing is listed."):
    return {
        "schema_version": 1,
        "title": title,
        "subtype": subtype,
        "sections": [
            {
                "heading": "Summary",
                "blocks": [{"type": "paragraph", "text": text, "evidence": list(evidence)}],
            }
        ],
        "warnings": [],
    }


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.CASE_DRAFTING_ENABLED = True


@pytest.fixture
def anil():
    return User.objects.create_user(username="ca-anil", password="pw-12345")


@pytest.fixture
def other():
    return User.objects.create_user(username="ca-other", password="pw-12345")


@pytest.fixture
def api(anil):
    client = APIClient()
    client.force_authenticate(user=anil)
    return client


@pytest.fixture
def other_api(other):
    client = APIClient()
    client.force_authenticate(user=other)
    return client


@pytest.fixture
def case(anil):
    return Case.objects.create(owner=anil, title="Rao vs State", case_number="OS/101/2026")


@pytest.fixture
def case2(anil):
    return Case.objects.create(owner=anil, title="Mehta vs Union", case_number="OS/102/2026")


def make_doc(owner, case, name="order.pdf"):
    return Document.objects.create(owner=owner, case=case, filename=name, file_path=f"x/{name}")


def make_message(owner):
    conv = Conversation.objects.create(owner=owner, scope="practice")
    return Message.objects.create(owner=owner, conversation=conv, role="user", content="hi")


def payload(case, rid="req-1", **extra):
    return {"case_id": case.id, "subtype": "status_memo", "client_request_id": rid, **extra}


def make_draft(owner, case, status="queued", subtype="status_memo", rid=None):
    return AssistantDraft.objects.create(
        owner=owner,
        case=case,
        kind=AssistantDraft.KIND_FOR_SUBTYPE[subtype],
        subtype=subtype,
        status=status,
        brief={},
        client_request_id=rid or f"r-{AssistantDraft.objects.count()}",
    )


def make_ready(owner, case, subtype="status_memo"):
    draft = make_draft(owner, case, status="ready", subtype=subtype)
    rev = AssistantDraftRevision.objects.create(
        owner=owner, draft=draft, version=1, body=body(subtype), evidence=EVIDENCE,
        missing_facts=["Client phone"], source="generated",
    )
    draft.current_revision = rev
    draft.save(update_fields=["current_revision"])
    return draft, rev


class TestGate:
    def test_flag_off_is_404_everywhere(self, api, anil, case, settings):
        draft, rev = make_ready(anil, case)
        settings.CASE_DRAFTING_ENABLED = False
        assert api.get(BASE, {"case_id": case.id}).status_code == 404
        assert api.post(BASE, payload(case), format="json").status_code == 404
        assert api.get(f"{BASE}{draft.id}/").status_code == 404
        assert api.get(f"{BASE}{draft.id}/revisions/1/").status_code == 404
        assert api.post(f"{BASE}{draft.id}/revisions/", {}, format="json").status_code == 404
        assert api.post(f"{BASE}{draft.id}/retry/", {}, format="json").status_code == 404

    def test_unauthenticated_is_401(self, case):
        client = APIClient()
        assert client.get(BASE, {"case_id": case.id}).status_code == 401
        assert client.post(BASE, payload(case), format="json").status_code == 401
        assert client.get(f"{BASE}1/").status_code == 401


class TestCreate:
    def test_happy_path(self, api, anil, case):
        doc = make_doc(anil, case)
        res = api.post(
            BASE,
            payload(case, source_document_ids=[doc.id, doc.id], instructions="Be brief"),
            format="json",
        )
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "queued" and data["generation"] == 1
        assert data["kind"] == "document" and data["case_title"] == "Rao vs State"
        assert data["brief"] == {
            "instructions": "Be brief", "audience": "", "tone": "neutral",
            "length": "standard", "source_document_ids": [doc.id],
        }
        assert data["current_revision"] is None and data["revisions"] == [] and data["outputs"] == []
        draft = AssistantDraft.objects.get(pk=data["id"])
        job = ProcessingJob.objects.get(job_type="draft_generation")
        assert job.payload == {"draft_id": draft.id, "generation": 1}
        assert draft.job_id == job.id and draft.owner == anil

    def test_note_kind_and_origin_message(self, api, anil, case):
        msg = make_message(anil)
        res = api.post(
            BASE,
            {**payload(case), "subtype": "personal_note", "origin_message_id": msg.id},
            format="json",
        )
        assert res.status_code == 202 and res.json()["kind"] == "note"
        draft = AssistantDraft.objects.get(pk=res.json()["id"])
        assert draft.origin_message_id == msg.id and draft.origin_conversation_id == msg.conversation_id

    def test_replay_same_payload(self, api, case):
        first = api.post(BASE, payload(case), format="json")
        second = api.post(BASE, payload(case), format="json")
        assert first.status_code == 202 and second.status_code == 200
        assert first.json()["id"] == second.json()["id"]
        assert AssistantDraft.objects.count() == 1
        assert ProcessingJob.objects.filter(job_type="draft_generation").count() == 1

    def test_replay_different_payload(self, api, case):
        api.post(BASE, payload(case), format="json")
        res = api.post(BASE, payload(case, instructions="different"), format="json")
        assert res.status_code == 409 and res.json()["code"] == "request_mismatch"

    def test_invalid_request(self, api, case):
        res = api.post(BASE, {**payload(case), "subtype": "nope"}, format="json")
        assert res.status_code == 400

    def test_foreign_case_404(self, api, other):
        theirs = Case.objects.create(owner=other, title="Theirs", case_number="OS/1/2026")
        assert api.post(BASE, payload(theirs), format="json").status_code == 404
        assert AssistantDraft.objects.count() == 0

    def test_foreign_document_404(self, api, other, case):
        theirs = Case.objects.create(owner=other, title="Theirs", case_number="OS/1/2026")
        doc = make_doc(other, theirs)
        res = api.post(BASE, payload(case, source_document_ids=[doc.id]), format="json")
        assert res.status_code == 404 and AssistantDraft.objects.count() == 0

    def test_own_document_of_other_case_404(self, api, anil, case, case2):
        doc = make_doc(anil, case2)
        res = api.post(BASE, payload(case, source_document_ids=[doc.id]), format="json")
        assert res.status_code == 404

    def test_foreign_origin_message_404(self, api, other, case):
        msg = make_message(other)
        res = api.post(BASE, payload(case, origin_message_id=msg.id), format="json")
        assert res.status_code == 404

    def test_pending_limit(self, api, anil, case):
        for _ in range(3):
            make_draft(anil, case)
        res = api.post(BASE, payload(case, rid="new"), format="json")
        assert res.status_code == 429 and res.json()["code"] == "draft_limit"

    def test_ready_drafts_do_not_count_toward_limit(self, api, anil, case):
        for _ in range(3):
            make_ready(anil, case)
        assert api.post(BASE, payload(case, rid="new"), format="json").status_code == 202


class TestRead:
    def test_list_scoped_and_ordered(self, api, anil, other, case, case2):
        older, _ = make_ready(anil, case)
        newer = make_draft(anil, case)
        make_draft(anil, case2)
        theirs = Case.objects.create(owner=other, title="T", case_number="OS/9/2026")
        make_draft(other, theirs)
        res = api.get(BASE, {"case_id": case.id})
        assert res.status_code == 200
        rows = res.json()
        assert [r["id"] for r in rows] == [newer.id, older.id]
        assert rows[1]["title"] == "Status" and rows[1]["current_version"] == 1
        assert rows[0]["title"] == "" and rows[0]["current_version"] is None

    def test_list_requires_case_and_ownership(self, api, other):
        assert api.get(BASE).status_code == 400
        theirs = Case.objects.create(owner=other, title="T", case_number="OS/9/2026")
        assert api.get(BASE, {"case_id": theirs.id}).status_code == 404

    def test_list_query_count_bounded(self, api, anil, case):
        for _ in range(6):
            make_ready(anil, case)
        with CaptureQueriesContext(connection) as ctx:
            assert len(api.get(BASE, {"case_id": case.id}).json()) == 6
        assert len(ctx) <= 8

    def test_detail(self, api, anil, case):
        draft, rev = make_ready(anil, case)
        data = api.get(f"{BASE}{draft.id}/").json()
        assert data["current_revision"]["id"] == rev.id
        assert data["current_revision"]["missing_facts"] == ["Client phone"]
        assert [r["version"] for r in data["revisions"]] == [1]
        assert data["approved_revision_id"] is None

    def test_detail_foreign_404(self, other_api, anil, case):
        draft, _ = make_ready(anil, case)
        assert other_api.get(f"{BASE}{draft.id}/").status_code == 404
        assert other_api.get(f"{BASE}{draft.id}/revisions/1/").status_code == 404

    def test_revision_by_version(self, api, anil, case):
        draft, rev = make_ready(anil, case)
        assert api.get(f"{BASE}{draft.id}/revisions/1/").json()["id"] == rev.id
        assert api.get(f"{BASE}{draft.id}/revisions/9/").status_code == 404


class TestRevisionSave:
    def url(self, draft):
        return f"{BASE}{draft.id}/revisions/"

    def test_happy_path(self, api, anil, case):
        draft, rev = make_ready(anil, case)
        new_body = body(title="Edited", text="Changed text.")
        new_body["warnings"] = ["Check the date"]
        res = api.post(self.url(draft), {"expected_revision": rev.id, "body": new_body}, format="json")
        assert res.status_code == 201
        data = res.json()
        assert data["current_revision"]["version"] == 2
        assert data["current_revision"]["source"] == "edited"
        assert data["current_revision"]["warnings"] == ["Check the date"]
        assert data["current_revision"]["missing_facts"] == ["Client phone"]
        assert [r["version"] for r in data["revisions"]] == [1, 2]
        draft.refresh_from_db()
        assert draft.current_revision_id == data["current_revision"]["id"]
        rev.refresh_from_db()
        assert rev.body["title"] == "Status"

    def test_identical_body_creates_nothing(self, api, anil, case):
        draft, rev = make_ready(anil, case)
        res = api.post(self.url(draft), {"expected_revision": rev.id, "body": rev.body}, format="json")
        assert res.status_code == 200 and res.json()["current_revision"]["id"] == rev.id
        assert draft.revisions.count() == 1

    def test_stale_revision(self, api, anil, case):
        draft, rev = make_ready(anil, case)
        res = api.post(self.url(draft), {"expected_revision": rev.id + 999, "body": body()}, format="json")
        assert res.status_code == 409
        assert res.json()["code"] == "stale_revision" and res.json()["current_revision_id"] == rev.id

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda b: b.update(extra="x"),
            lambda b: b["sections"][0]["blocks"][0].update(text="<b>bold</b>"),
            lambda b: b["sections"][0]["blocks"][0].update(evidence=["hearing:999"]),
        ],
        ids=["unknown_field", "markup", "evidence_not_collected"],
    )
    def test_invalid_body(self, api, anil, case, mutate):
        draft, rev = make_ready(anil, case)
        bad = copy.deepcopy(body())
        mutate(bad)
        res = api.post(self.url(draft), {"expected_revision": rev.id, "body": bad}, format="json")
        assert res.status_code == 400
        assert res.json()["code"] == "invalid_body" and res.json()["errors"]
        assert draft.revisions.count() == 1

    def test_wrong_subtype(self, api, anil, case):
        draft, rev = make_ready(anil, case)
        res = api.post(
            self.url(draft),
            {"expected_revision": rev.id, "body": body(subtype="personal_note")},
            format="json",
        )
        assert res.status_code == 400 and res.json()["code"] == "invalid_body"

    def test_not_ready_is_409(self, api, anil, case):
        draft = make_draft(anil, case, status="generating")
        res = api.post(self.url(draft), {"expected_revision": 1, "body": body()}, format="json")
        assert res.status_code == 409 and res.json()["code"] == "not_ready"

    def test_foreign_draft_404(self, other_api, anil, case):
        draft, rev = make_ready(anil, case)
        res = other_api.post(self.url(draft), {"expected_revision": rev.id, "body": body()}, format="json")
        assert res.status_code == 404


class TestRetry:
    def url(self, draft):
        return f"{BASE}{draft.id}/retry/"

    def test_failed_is_requeued(self, api, anil, case):
        draft = make_draft(anil, case, status="failed")
        draft.error = "Generation failed."
        draft.save()
        res = api.post(self.url(draft), {}, format="json")
        assert res.status_code == 202
        data = res.json()
        assert data["status"] == "queued" and data["generation"] == 2 and data["error"] == ""
        job = ProcessingJob.objects.get(job_type="draft_generation")
        assert job.payload == {"draft_id": draft.id, "generation": 2}
        draft.refresh_from_db()
        assert draft.job_id == job.id

    def test_ready_is_409(self, api, anil, case):
        draft, _ = make_ready(anil, case)
        res = api.post(self.url(draft), {}, format="json")
        assert res.status_code == 409 and res.json()["code"] == "not_retryable"

    def test_queued_returns_same_job(self, api, anil, case):
        first = api.post(BASE, payload(case), format="json").json()
        draft = AssistantDraft.objects.get(pk=first["id"])
        job_id = draft.job_id
        res = api.post(self.url(draft), {}, format="json")
        assert res.status_code == 200 and res.json()["generation"] == 1
        draft.refresh_from_db()
        assert draft.job_id == job_id
        assert ProcessingJob.objects.filter(job_type="draft_generation").count() == 1

    def test_limit_applies(self, api, anil, case):
        failed = make_draft(anil, case, status="failed")
        for _ in range(3):
            make_draft(anil, case)
        res = api.post(self.url(failed), {}, format="json")
        assert res.status_code == 429 and res.json()["code"] == "draft_limit"

    def test_foreign_draft_404(self, other_api, anil, case):
        draft = make_draft(anil, case, status="failed")
        assert other_api.post(self.url(draft), {}, format="json").status_code == 404
