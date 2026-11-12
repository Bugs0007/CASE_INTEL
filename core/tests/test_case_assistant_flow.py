"""The whole drafting flow through the real endpoints and the real worker
entry point: brief -> generation job -> edit -> approve -> DOCX and note.

Each stage has its own detailed suite (test_case_assistant_api.py,
test_draft_generation.py, test_draft_approval_outputs.py). This file only
proves the pieces fit together. Provider and storage are fakes.
"""
import hashlib
import io
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.storage import InMemoryStorage
from django.test import override_settings
from django.utils import timezone
from docx import Document as DocxDocument
from rest_framework.test import APIClient

from core.management.commands.process_jobs import MAX_ATTEMPTS, Command
from core.models import AssistantDraft, Case, CaseNote, Hearing, ProcessingJob
from core.services.drafting.generate import run_draft_generation
from core.services.drafting.schema import SCHEMA_VERSION

pytestmark = pytest.mark.django_db


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def generate_with_json(self, messages, temperature=0.1, max_tokens=4096):
        self.calls += 1
        return self.reply(messages) if callable(self.reply) else self.reply


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _body(evidence_ids, title="Status of the matter"):
    return {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "subtype": "status_memo",
        "sections": [
            {
                "heading": "Current status",
                "blocks": [
                    {"type": "paragraph", "text": "The matter is listed next week.",
                     "evidence": list(evidence_ids), "is_suggestion": False},
                    {"type": "bullets", "items": ["Consider filing a reply."],
                     "evidence": [], "is_suggestion": True},
                ],
            }
        ],
        "verification_items": [],
        "warnings": [],
    }


@override_settings(CASE_DRAFTING_ENABLED=True)
def test_brief_to_docx_and_note():
    owner = User.objects.create_user(username="flow-owner", password="pass-12345")
    case = Case.objects.create(
        owner=owner, title="Rao vs State", case_number="WP/101/2026",
        client_name="Rao", petitioner_name="K. Rao", respondent_name="State of Telangana",
    )
    hearing = Hearing.objects.create(
        owner=owner, case=case, hearing_type="status",
        hearing_date=timezone.now() + timedelta(days=5),
    )
    client = _client(owner)

    # 1. Brief
    created = client.post(
        "/api/case-assistant/drafts/",
        {"case_id": case.id, "subtype": "status_memo",
         "instructions": "Short status for the client", "client_request_id": "flow-1"},
        format="json",
    )
    assert created.status_code == 202, created.content
    draft_id = created.json()["id"]
    assert created.json()["status"] == "queued"
    job = ProcessingJob.objects.get(job_type="draft_generation")
    assert job.payload == {"draft_id": draft_id, "generation": 1}

    # 2. Worker
    fake = FakeLLM(json.dumps(_body([f"hearing:{hearing.id}", f"case:{case.id}"])))
    with patch("core.services.graph.draft_graph.get_llm_client", return_value=fake):
        assert run_draft_generation(job) == "committed"
    detail = client.get(f"/api/case-assistant/drafts/{draft_id}/").json()
    assert detail["status"] == "ready"
    revision = detail["current_revision"]
    assert revision["version"] == 1 and revision["source"] == "generated"
    assert {e["id"] for e in revision["evidence"]} >= {f"hearing:{hearing.id}", f"case:{case.id}"}

    # 3. Edit
    edited = dict(revision["body"], title="Status note for Mr Rao ₹")
    saved = client.post(
        f"/api/case-assistant/drafts/{draft_id}/revisions/",
        {"expected_revision": revision["id"], "body": edited},
        format="json",
    )
    assert saved.status_code == 201, saved.content
    current = saved.json()["current_revision"]
    assert current["version"] == 2 and current["source"] == "edited"

    # 4. Approve: the old revision is stale, the current one is approved.
    stale = client.post(
        f"/api/case-assistant/drafts/{draft_id}/approve/",
        {"revision_id": revision["id"], "acknowledge_open_items": True}, format="json",
    )
    assert stale.status_code == 409 and stale.json()["code"] == "stale_revision"
    approved = client.post(
        f"/api/case-assistant/drafts/{draft_id}/approve/",
        {"revision_id": current["id"], "acknowledge_open_items": True}, format="json",
    )
    assert approved.status_code == 200, approved.content
    assert approved.json()["approved_revision_id"] == current["id"]

    # 5. Outputs
    storage = InMemoryStorage()
    with patch("core.services.drafting.outputs.default_storage", storage):
        docx = client.post(
            f"/api/case-assistant/drafts/{draft_id}/outputs/",
            {"revision_id": current["id"], "destination": "docx"}, format="json",
        )
        assert docx.status_code == 201, docx.content
        assert docx.json()["status"] == "ready"
        download = client.get(f"/api/case-assistant/outputs/{docx.json()['id']}/download/")
        assert download.status_code == 200
        data = b"".join(download.streaming_content) if download.streaming else download.content
    text = "\n".join(p.text for p in DocxDocument(io.BytesIO(data)).paragraphs)
    assert "Status note for Mr Rao ₹" in text
    from core.models import DraftOutput
    assert hashlib.sha256(data).hexdigest() == DraftOutput.objects.get(id=docx.json()["id"]).checksum

    note = client.post(
        f"/api/case-assistant/drafts/{draft_id}/outputs/",
        {"revision_id": current["id"], "destination": "case_note"}, format="json",
    )
    assert note.status_code == 201, note.content
    notes = client.get(f"/api/cases/{case.id}/notes/").json()
    assert [n["title"] for n in notes] == ["Status note for Mr Rao ₹"]
    assert notes[0]["origin_draft_id"] == draft_id
    assert CaseNote.objects.filter(owner=owner, case=case).count() == 1

    # The provider was called once, and only by the worker.
    assert fake.calls == 1


def test_job_that_keeps_killing_the_worker_fails_its_draft():
    owner = User.objects.create_user(username="flow-crash", password="pass-12345")
    case = Case.objects.create(owner=owner, title="A vs B", client_name="A")
    draft = AssistantDraft.objects.create(
        owner=owner, case=case, kind="document", subtype="status_memo",
        status=AssistantDraft.STATUS_GENERATING, brief={}, client_request_id="crash-1",
    )
    job, _ = ProcessingJob.enqueue_draft_generation(draft)
    ProcessingJob.objects.filter(id=job.id).update(
        status="running", attempts=MAX_ATTEMPTS,
        updated_at=timezone.now() - timedelta(hours=1),
    )

    Command()._reclaim_stale_jobs(60)

    job.refresh_from_db()
    draft.refresh_from_db()
    assert job.status == "failed"
    assert draft.status == AssistantDraft.STATUS_FAILED
    assert draft.error == "The draft could not be generated. Try again."
