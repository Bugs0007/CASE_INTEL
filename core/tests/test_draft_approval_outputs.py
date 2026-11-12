"""Approval of a draft revision, its outputs (DOCX, case note), the
authenticated download and the case-notes endpoints.

Storage is an in-memory fake patched where the outputs service looks it up,
so nothing here writes to the media directory or S3.
"""

import copy
import hashlib
import io
import uuid
from datetime import date, datetime
from datetime import timezone as dt_timezone
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import InMemoryStorage
from docx import Document as DocxDocument
from rest_framework.test import APIClient

from core.models import (
    AssistantDraft,
    AssistantDraftRevision,
    Case,
    CaseEvent,
    CaseNote,
    Document,
    DraftOutput,
    Hearing,
    Task,
)
from core.services.drafting import docx_render, outputs
from core.services.drafting.approval import approve_revision, body_hash
from core.services.drafting.outputs import body_to_text

pytestmark = pytest.mark.django_db

TELUGU = "తదుపరి విచారణ"
HINDI = "अगली सुनवाई"


class CountingStorage(InMemoryStorage):
    def __init__(self):
        super().__init__()
        self.saves = 0
        self.fail_next = False

    def save(self, name, content, max_length=None):
        if self.fail_next:
            self.fail_next = False
            raise OSError("disk full")
        self.saves += 1
        return super().save(name, content, max_length=max_length)


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.CASE_DRAFTING_ENABLED = True


@pytest.fixture(autouse=True)
def storage():
    fake = CountingStorage()
    with patch.object(outputs, "default_storage", fake):
        yield fake


@pytest.fixture
def anil():
    return User.objects.create_user("anil", password="x")


@pytest.fixture
def bina():
    return User.objects.create_user("bina", password="x")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def api(anil):
    return client_for(anil)


def make_case(owner, number="WP/100/2026", title="Rao v. State"):
    return Case.objects.create(owner=owner, case_number=number, title=title, client_name="Rao")


def make_body(*, title="Status memo for Rao", verification_items=None, marker="original"):
    body = {
        "schema_version": 1,
        "title": title,
        "subtype": "status_memo",
        "sections": [
            {
                "heading": "Where the matter stands",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": f"The {marker} position. {HINDI}. Costs of ₹5,000 were paid.",
                        "evidence": ["hearing:H"],
                    },
                    {"type": "bullets", "items": ["File the counter", TELUGU], "evidence": ["task:T"]},
                    {
                        "type": "table",
                        "columns": ["Date", "Event"],
                        "rows": [["12 Nov 2026", "Arguments"], ["20 Nov 2026", "Orders"]],
                    },
                    {"type": "paragraph", "text": "Press for an early date.", "is_suggestion": True},
                ],
            }
        ],
    }
    if verification_items:
        body["verification_items"] = verification_items
    return body


def _entry(kind, record_id, case_id, label, evidence_id):
    return {
        "id": evidence_id,
        "kind": kind,
        "label": label,
        "ref": {"kind": kind, "id": record_id, "case_id": case_id, "label": label, "recorded_at": None},
        "fingerprint": "f",
    }


def make_draft(owner, case=None, *, body=None, missing_facts=None, status=AssistantDraft.STATUS_READY):
    """A ready draft with one generated revision citing a hearing, a task,
    an event, a document and the case itself."""
    case = case or make_case(owner, number=f"WP/{uuid.uuid4().hex[:6]}/2026")
    hearing = Hearing.objects.create(
        owner=owner, case=case, hearing_date=datetime(2026, 11, 12, tzinfo=dt_timezone.utc), hearing_type="other"
    )
    task = Task.objects.create(owner=owner, case=case, title="File counter", due_date=date(2026, 11, 10))
    event = CaseEvent.objects.create(owner=owner, case=case, title="Mediation", date=date(2026, 11, 14))
    document = Document.objects.create(
        owner=owner, case=case, filename="order.pdf", file_path="documents/order.pdf", file_type="pdf", file_size=10
    )
    evidence = [
        _entry("case", case.id, case.id, "The case record", "case:C"),
        _entry("hearing", hearing.id, case.id, "Hearing on 12 Nov 2026", "hearing:H"),
        _entry("task", task.id, case.id, "Task: File counter", "task:T"),
        _entry("event", event.id, case.id, "Event: Mediation", "event:E"),
        _entry("document", document.id, case.id, "order.pdf", "doc:D"),
    ]
    draft = AssistantDraft.objects.create(
        owner=owner,
        case=case,
        kind=AssistantDraft.KIND_DOCUMENT,
        subtype=AssistantDraft.SUBTYPE_STATUS_MEMO,
        status=status,
        client_request_id=uuid.uuid4().hex,
    )
    revision = AssistantDraftRevision.objects.create(
        owner=owner,
        draft=draft,
        version=1,
        body=body or make_body(),
        evidence=evidence,
        missing_facts=missing_facts or [],
        source=AssistantDraftRevision.SOURCE_GENERATED,
    )
    draft.current_revision = revision
    draft.save()
    return {
        "draft": draft,
        "revision": revision,
        "case": case,
        "hearing": hearing,
        "task": task,
        "event": event,
        "document": document,
    }


def add_revision(draft, body):
    previous = draft.current_revision
    revision = AssistantDraftRevision.objects.create(
        owner=draft.owner,
        draft=draft,
        version=previous.version + 1,
        body=body,
        evidence=previous.evidence,
        source=AssistantDraftRevision.SOURCE_EDITED,
    )
    draft.current_revision = revision
    draft.save()
    return revision


def approve_url(draft):
    return f"/api/case-assistant/drafts/{draft.id}/approve/"


def outputs_url(draft):
    return f"/api/case-assistant/drafts/{draft.id}/outputs/"


def download_url(output_id):
    return f"/api/case-assistant/outputs/{output_id}/download/"


def approve(api, made, **extra):
    return api.post(approve_url(made["draft"]), {"revision_id": made["revision"].id, **extra}, format="json")


def release(api, made, destination, revision=None):
    revision = revision or made["revision"]
    return api.post(
        outputs_url(made["draft"]), {"revision_id": revision.id, "destination": destination}, format="json"
    )


def docx_text(data: bytes) -> str:
    doc = DocxDocument(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    return "\n".join(parts)


class TestApprove:
    def test_happy_path_sets_the_three_fields(self, api, anil):
        made = make_draft(anil)
        response = approve(api, made)
        assert response.status_code == 200, response.content
        revision = AssistantDraftRevision.objects.get(pk=made["revision"].id)
        assert revision.approved_at is not None
        assert revision.approved_by_id == anil.id
        assert revision.approved_hash == body_hash(revision.body)
        assert len(revision.approved_hash) == 64
        payload = response.json()
        assert payload["id"] == made["draft"].id
        assert payload["approved_revision_id"] == revision.id
        assert payload["current_revision"]["approved_hash"] == revision.approved_hash
        assert payload["current_revision"]["approved_at"] is not None

    def test_double_approve_is_one_approval(self, api, anil):
        made = make_draft(anil)
        first = approve(api, made)
        stamped = AssistantDraftRevision.objects.get(pk=made["revision"].id)
        second = approve(api, made)
        assert first.status_code == second.status_code == 200
        again = AssistantDraftRevision.objects.get(pk=made["revision"].id)
        assert again.approved_at == stamped.approved_at
        assert again.approved_hash == stamped.approved_hash
        assert second.json()["current_revision"]["approved_at"] == first.json()["current_revision"]["approved_at"]

    def test_service_called_twice_keeps_the_first_approval(self, anil):
        made = make_draft(anil)
        kwargs = dict(draft_id=made["draft"].id, revision_id=made["revision"].id, user=anil)
        approve_revision(**kwargs)
        stamped = AssistantDraftRevision.objects.get(pk=made["revision"].id).approved_at
        approve_revision(**kwargs)
        assert AssistantDraftRevision.objects.get(pk=made["revision"].id).approved_at == stamped
        assert AssistantDraftRevision.objects.filter(approved_at__isnull=False).count() == 1

    def test_non_current_revision_is_stale(self, api, anil):
        made = make_draft(anil)
        newer = add_revision(made["draft"], make_body(marker="edited"))
        response = approve(api, made)
        assert response.status_code == 409
        assert response.json()["code"] == "stale_revision"
        assert response.json()["current_revision_id"] == newer.id
        assert AssistantDraftRevision.objects.get(pk=made["revision"].id).approved_at is None

    def test_draft_that_is_not_ready_cannot_be_approved(self, api, anil):
        made = make_draft(anil, status=AssistantDraft.STATUS_GENERATING)
        response = approve(api, made)
        assert response.status_code == 409
        assert response.json()["code"] == "stale_revision"

    def test_open_items_need_acknowledgement(self, api, anil):
        made = make_draft(anil, body=make_body(verification_items=["Confirm the costs amount"]))
        refused = approve(api, made)
        assert refused.status_code == 409
        assert refused.json()["code"] == "needs_acknowledgement"
        assert refused.json()["items"] == ["Confirm the costs amount"]
        assert approve(api, made, acknowledge_open_items="yes").status_code == 409
        assert approve(api, made, acknowledge_open_items=True).status_code == 200

    def test_missing_facts_need_acknowledgement(self, api, anil):
        made = make_draft(anil, missing_facts=["No next date is recorded"])
        refused = approve(api, made)
        assert refused.json()["code"] == "needs_acknowledgement"
        assert refused.json()["items"] == ["No next date is recorded"]
        assert approve(api, made, acknowledge_open_items=True).status_code == 200

    @pytest.mark.parametrize("gone, label", [("hearing", "Hearing on 12 Nov 2026"), ("task", "Task: File counter")])
    def test_deleted_record_is_evidence_changed(self, api, anil, gone, label):
        made = make_draft(anil)
        made[gone].delete()
        response = approve(api, made)
        assert response.status_code == 409
        assert response.json()["code"] == "evidence_changed"
        assert response.json()["items"] == [label]
        assert AssistantDraftRevision.objects.get(pk=made["revision"].id).approved_at is None

    def test_document_moved_to_another_case_is_evidence_changed(self, api, anil):
        made = make_draft(anil)
        made["document"].case = make_case(anil, number="OS/7/2026", title="Other")
        made["document"].save()
        response = approve(api, made)
        assert response.status_code == 409
        assert response.json()["code"] == "evidence_changed"
        assert response.json()["items"] == ["order.pdf"]

    def test_deleted_document_is_evidence_changed(self, api, anil):
        made = make_draft(anil)
        made["document"].delete()
        response = approve(api, made)
        assert response.json()["code"] == "evidence_changed"
        assert response.json()["items"] == ["order.pdf"]

    def test_body_that_no_longer_validates_is_refused(self, api, anil):
        made = make_draft(anil)
        body = make_body()
        body["sections"][0]["blocks"][0]["evidence"] = ["hearing:999"]
        AssistantDraftRevision.objects.filter(pk=made["revision"].id).update(body=body)
        response = approve(api, made)
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_body"

    def test_foreign_and_mismatched_ids_are_404(self, api, anil, bina):
        mine = make_draft(anil)
        other_of_mine = make_draft(anil)
        theirs = make_draft(bina)
        # another owner's draft
        assert approve(api, theirs).status_code == 404
        # my draft, another owner's revision id
        cross = api.post(approve_url(mine["draft"]), {"revision_id": theirs["revision"].id}, format="json")
        assert cross.status_code == 404
        # my draft, a revision of my other draft
        mixed = api.post(approve_url(mine["draft"]), {"revision_id": other_of_mine["revision"].id}, format="json")
        assert mixed.status_code == 404
        assert api.post(approve_url(mine["draft"]), {"revision_id": 999999}, format="json").status_code == 404
        assert not AssistantDraftRevision.objects.filter(approved_at__isnull=False).exists()

    def test_missing_revision_id_is_400(self, api, anil):
        made = make_draft(anil)
        assert api.post(approve_url(made["draft"]), {}, format="json").status_code == 400


class TestEditAfterApproval:
    def test_old_approval_cannot_release_new_text(self, api, anil):
        made = make_draft(anil)
        assert approve(api, made).status_code == 200
        newer = add_revision(made["draft"], make_body(marker="rewritten"))

        for destination in ("docx", "case_note"):
            refused = release(api, made, destination, revision=newer)
            assert refused.status_code == 409
            assert refused.json()["code"] == "not_approved"
        assert not DraftOutput.objects.exists()

        old = release(api, made, "docx")
        assert old.status_code == 201
        text = docx_text(api.get(download_url(old.json()["id"])).content)
        assert "The original position." in text
        assert "rewritten" not in text

        note = release(api, made, "case_note")
        assert note.status_code == 201
        saved = CaseNote.objects.get()
        assert "original" in saved.body and "rewritten" not in saved.body

    def test_changed_body_under_an_approval_is_not_released(self, api, anil):
        made = make_draft(anil)
        approve(api, made)
        AssistantDraftRevision.objects.filter(pk=made["revision"].id).update(body=make_body(marker="tampered"))
        refused = release(api, made, "docx")
        assert refused.status_code == 409
        assert refused.json()["code"] == "not_approved"

    def test_unapproved_revision_has_no_outputs(self, api, anil, storage):
        made = make_draft(anil)
        refused = release(api, made, "docx")
        assert refused.status_code == 409
        assert refused.json()["code"] == "not_approved"
        assert storage.saves == 0


class TestDocxOutput:
    def test_created_once_and_downloadable(self, api, anil, storage):
        made = make_draft(anil, body=make_body(verification_items=["Confirm the costs amount"]))
        approve(api, made, acknowledge_open_items=True)

        first = release(api, made, "docx")
        assert first.status_code == 201, first.content
        payload = first.json()
        assert payload["destination"] == "docx"
        assert payload["status"] == "ready"
        assert payload["revision_id"] == made["revision"].id
        assert payload["filename"] == "Status memo for Rao.docx"
        assert payload["case_note_id"] is None
        assert "file_path" not in payload and "url" not in payload

        second = release(api, made, "docx")
        assert second.status_code == 200
        assert second.json()["id"] == payload["id"]
        assert storage.saves == 1
        assert DraftOutput.objects.count() == 1

        output = DraftOutput.objects.get()
        assert output.file_path == f"draft_outputs/{anil.id}/{made['draft'].id}/r1.docx"

        download = api.get(download_url(output.id))
        assert download.status_code == 200
        assert download["Content-Type"] == outputs.DOCX_CONTENT_TYPE
        assert download["Content-Disposition"] == 'attachment; filename="Status memo for Rao.docx"'
        assert download["Cache-Control"] == "private, no-store"
        assert hashlib.sha256(download.content).hexdigest() == output.checksum

        doc = DocxDocument(io.BytesIO(download.content))
        paragraphs = [p.text for p in doc.paragraphs]
        assert "Status memo for Rao" in paragraphs
        assert "Where the matter stands" in paragraphs
        assert any(p.style.name.startswith("Heading") and p.text == "Where the matter stands" for p in doc.paragraphs)
        assert any(p.style.name == "List Bullet" and p.text == "File the counter" for p in doc.paragraphs)
        assert any(p.style.name == "List Bullet" and p.text == TELUGU for p in doc.paragraphs)
        assert doc.tables[0].rows[0].cells[1].text == "Event"
        assert doc.tables[0].rows[1].cells[1].text == "Arguments"
        text = "\n".join(paragraphs)
        assert HINDI in text and "₹5,000" in text
        assert "Suggestion: Press for an early date." in paragraphs
        assert "Items to verify" in paragraphs and "Confirm the costs amount" in paragraphs
        assert any(made["case"].case_number in p for p in paragraphs)
        assert any("approved draft, version 1" in p for p in paragraphs)

    def test_same_revision_renders_identical_bytes(self, api, anil):
        made = make_draft(anil)
        approve(api, made)
        revision = AssistantDraftRevision.objects.select_related("draft__case").get(pk=made["revision"].id)
        assert docx_render.render_docx(revision) == docx_render.render_docx(revision)

    def test_non_ascii_title_gets_an_ascii_filename(self, api, anil):
        made = make_draft(anil, body=make_body(title=f'{TELUGU} / memo: "Rao"'))
        approve(api, made)
        filename = release(api, made, "docx").json()["filename"]
        assert filename == "memo Rao.docx"
        assert filename.isascii()

    def test_storage_failure_leaves_no_ready_row_and_retry_succeeds(self, api, anil, storage):
        made = make_draft(anil)
        approve(api, made)
        storage.fail_next = True

        failed = release(api, made, "docx")
        assert failed.status_code == 502
        assert failed.json() == {"detail": "The file could not be saved. Try again."}
        row = DraftOutput.objects.get()
        assert row.status == DraftOutput.STATUS_FAILED
        assert row.error == "The file could not be saved. Try again."
        assert row.file_path == "" and row.checksum == ""
        assert not DraftOutput.objects.filter(status=DraftOutput.STATUS_READY).exists()
        assert api.get(download_url(row.id)).status_code == 404

        retry = release(api, made, "docx")
        assert retry.status_code == 201
        assert retry.json()["id"] == row.id
        assert retry.json()["status"] == "ready"
        assert retry.json()["error"] == ""
        assert DraftOutput.objects.count() == 1
        assert api.get(download_url(row.id)).status_code == 200

    def test_stale_pending_row_is_finished_in_place(self, api, anil):
        made = make_draft(anil)
        approve(api, made)
        pending = DraftOutput.objects.create(
            owner=anil, revision=made["revision"], destination=DraftOutput.DEST_DOCX
        )
        response = release(api, made, "docx")
        assert response.status_code == 201
        assert response.json()["id"] == pending.id
        assert DraftOutput.objects.get().status == DraftOutput.STATUS_READY

    def test_bad_request_bodies(self, api, anil):
        made = make_draft(anil)
        approve(api, made)
        assert release(api, made, "pdf").status_code == 400
        assert api.post(outputs_url(made["draft"]), {"destination": "docx"}, format="json").status_code == 400

    def test_foreign_and_mismatched_ids_are_404(self, api, anil, bina):
        mine = make_draft(anil)
        other_of_mine = make_draft(anil)
        theirs = make_draft(bina)
        approve(client_for(bina), theirs)
        approve(api, other_of_mine)
        assert release(api, theirs, "docx").status_code == 404
        assert release(api, mine, "docx", revision=theirs["revision"]).status_code == 404
        assert release(api, mine, "docx", revision=other_of_mine["revision"]).status_code == 404
        assert not DraftOutput.objects.exists()


class TestDownload:
    def test_other_owner_note_output_and_pending_are_404(self, api, anil, bina):
        made = make_draft(anil)
        approve(api, made)
        docx_id = release(api, made, "docx").json()["id"]
        note_id = release(api, made, "case_note").json()["id"]

        assert client_for(bina).get(download_url(docx_id)).status_code == 404
        assert api.get(download_url(note_id)).status_code == 404
        assert api.get(download_url(999999)).status_code == 404

        other = make_draft(anil)
        pending = DraftOutput.objects.create(
            owner=anil, revision=other["revision"], destination=DraftOutput.DEST_DOCX
        )
        assert api.get(download_url(pending.id)).status_code == 404

    def test_missing_file_is_404(self, api, anil, storage):
        made = make_draft(anil)
        approve(api, made)
        output = DraftOutput.objects.get(pk=release(api, made, "docx").json()["id"])
        storage.delete(output.file_path)
        assert api.get(download_url(output.id)).status_code == 404


class TestCaseNoteOutput:
    def test_one_note_on_the_right_case(self, api, anil):
        made = make_draft(anil)
        approve(api, made)
        first = release(api, made, "case_note")
        assert first.status_code == 201, first.content
        note = CaseNote.objects.get()
        assert note.owner_id == anil.id
        assert note.case_id == made["case"].id
        assert note.title == "Status memo for Rao"
        approved_body = AssistantDraftRevision.objects.get(pk=made["revision"].id).body
        assert note.body == body_to_text(approved_body)
        assert note.origin_revision_id == made["revision"].id
        assert first.json()["case_note_id"] == note.id
        assert first.json()["status"] == "ready"
        assert first.json()["filename"] == ""

        second = release(api, made, "case_note")
        assert second.status_code == 200
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["case_note_id"] == note.id
        assert CaseNote.objects.count() == 1

    def test_plain_text_rendering(self):
        text = body_to_text(make_body(verification_items=["Confirm the costs amount"]))
        lines = text.split("\n")
        assert lines[0] == "Where the matter stands"
        assert "- File the counter" in lines
        assert f"- {TELUGU}" in lines
        assert "Date | Event" in lines
        assert "12 Nov 2026 | Arguments" in lines
        assert "Suggestion: Press for an early date." in lines
        assert lines[-2:] == ["Items to verify", "- Confirm the costs amount"]

    def test_note_outlives_its_draft(self, api, anil):
        made = make_draft(anil)
        approve(api, made)
        release(api, made, "case_note")
        made["draft"].delete()

        note = CaseNote.objects.get()
        assert note.origin_revision_id is None
        listed = api.get(f"/api/cases/{made['case'].id}/notes/")
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [note.id]
        assert listed.json()[0]["origin_draft_id"] is None


class TestCaseNotes:
    def test_list_is_scoped_to_owner_and_case(self, api, anil, bina):
        made = make_draft(anil)
        approve(api, made)
        release(api, made, "case_note")
        other_case = make_case(anil, number="OS/9/2026", title="Other")
        older = CaseNote.objects.create(owner=anil, case=other_case, title="Elsewhere", body="x")
        theirs = make_draft(bina)
        CaseNote.objects.create(owner=bina, case=theirs["case"], title="Bina", body="y")

        listed = api.get(f"/api/cases/{made['case'].id}/notes/")
        assert listed.status_code == 200
        rows = listed.json()
        assert len(rows) == 1
        assert set(rows[0]) == {"id", "case_id", "title", "body", "origin_draft_id", "created_at", "updated_at"}
        assert rows[0]["case_id"] == made["case"].id
        assert rows[0]["origin_draft_id"] == made["draft"].id

        assert [r["id"] for r in api.get(f"/api/cases/{other_case.id}/notes/").json()] == [older.id]
        assert api.get(f"/api/cases/{theirs['case'].id}/notes/").status_code == 404

    def test_newest_first(self, api, anil):
        case = make_case(anil)
        first = CaseNote.objects.create(owner=anil, case=case, title="First", body="a")
        second = CaseNote.objects.create(owner=anil, case=case, title="Second", body="b")
        rows = api.get(f"/api/cases/{case.id}/notes/").json()
        assert [r["id"] for r in rows] == [second.id, first.id]

    def test_delete(self, api, anil, bina):
        case = make_case(anil)
        mine = CaseNote.objects.create(owner=anil, case=case, title="Mine", body="a")
        theirs = CaseNote.objects.create(
            owner=bina, case=make_case(bina, number="B/1/2026"), title="Theirs", body="b"
        )
        assert api.delete(f"/api/case-notes/{theirs.id}/").status_code == 404
        assert CaseNote.objects.filter(pk=theirs.id).exists()
        assert api.delete(f"/api/case-notes/{mine.id}/").status_code == 204
        assert not CaseNote.objects.filter(pk=mine.id).exists()
        assert api.delete(f"/api/case-notes/{mine.id}/").status_code == 404

    def test_saving_again_after_the_note_was_deleted_makes_a_new_note(self, api, anil):
        made = make_draft(anil)
        approve(api, made)
        first = release(api, made, "case_note").json()
        api.delete(f"/api/case-notes/{first['case_note_id']}/")
        again = release(api, made, "case_note")
        assert again.status_code == 201
        assert again.json()["id"] == first["id"]
        assert again.json()["case_note_id"] == CaseNote.objects.get().id


class TestFlagAndAuth:
    def test_flag_off_hides_approve_and_outputs_only(self, api, anil, settings):
        made = make_draft(anil)
        approve(api, made)
        docx_id = release(api, made, "docx").json()["id"]
        release(api, made, "case_note")
        fresh = make_draft(anil)

        settings.CASE_DRAFTING_ENABLED = False
        assert approve(api, fresh).status_code == 404
        assert AssistantDraftRevision.objects.get(pk=fresh["revision"].id).approved_at is None
        assert release(api, made, "docx").status_code == 404
        assert api.get(approve_url(fresh["draft"])).status_code == 404

        assert api.get(download_url(docx_id)).status_code == 200
        listed = api.get(f"/api/cases/{made['case'].id}/notes/")
        assert listed.status_code == 200 and len(listed.json()) == 1
        assert api.delete(f"/api/case-notes/{listed.json()[0]['id']}/").status_code == 204

    def test_unauthenticated_is_401(self, anil):
        made = make_draft(anil)
        anonymous = APIClient()
        body = {"revision_id": made["revision"].id, "destination": "docx"}
        assert anonymous.post(approve_url(made["draft"]), body, format="json").status_code == 401
        assert anonymous.post(outputs_url(made["draft"]), body, format="json").status_code == 401
        assert anonymous.get(download_url(1)).status_code == 401
        assert anonymous.get(f"/api/cases/{made['case'].id}/notes/").status_code == 401
        assert anonymous.delete("/api/case-notes/1/").status_code == 401
        assert AssistantDraftRevision.objects.get(pk=made["revision"].id).approved_at is None


def test_body_hash_is_canonical():
    body = make_body()
    reordered = dict(reversed(list(copy.deepcopy(body).items())))
    assert body_hash(body) == body_hash(reordered)
    assert body_hash(body) != body_hash(make_body(marker="other"))
