"""Worker claim order and lanes (core/management/commands/process_jobs.py).

A 100-case import queues one order_sync per case and then a document job per
downloaded order PDF -- hundreds of rows. They share a queue with an
advocate's own uploads, so the claim order, not just the queue, decides
whether an upload waits minutes or hours.
"""

import itertools
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from core.management.commands.process_jobs import Command
from core.models import Case, Document, ProcessingJob


@pytest.fixture
def owner(db):
    return User.objects.create_user(username="prio-owner", password="pw-12345")


@pytest.fixture
def case(owner):
    return Case.objects.create(owner=owner, case_number="OS/1/2026", title="t", client_name="")


_seq = itertools.count()


def _job(owner, *, job_type="document", document_type="other", case=None):
    """A queued job. Each call is created one minute after the previous one,
    so the order of the calls is the order the queue sees them in."""
    n = next(_seq)
    document = None
    if job_type == "document":
        document = Document.objects.create(
            owner=owner, filename="f.pdf", file_path=f"documents/{n}.pdf",
            file_type="pdf", file_size=1, document_type=document_type,
            processing_status="pending",
        )
    job = ProcessingJob.objects.create(owner=owner, job_type=job_type, document=document, case=case)
    ProcessingJob.objects.filter(id=job.id).update(
        created_at=timezone.now() - timezone.timedelta(days=1) + timezone.timedelta(minutes=n)
    )
    return job


@pytest.mark.django_db
class TestClaimOrder:
    def test_a_users_upload_beats_older_background_work(self, owner, case):
        # Oldest first: a refresh-all batch, 3 portal-fetched order PDFs, an order sync...
        bulk = _job(owner, job_type="tracking_refresh")
        order_sync = _job(owner, job_type="order_sync", case=case)
        fetched = [_job(owner, document_type="court_order") for _ in range(3)]
        # ...and only then the advocate's own upload.
        upload = _job(owner, document_type="other")

        claimed = [Command()._claim_next_job().id for _ in range(6)]

        assert claimed[0] == upload.id
        assert claimed[1:4] == [j.id for j in fetched]  # then fetched orders, oldest first
        assert set(claimed[4:]) == {bulk.id, order_sync.id}

    def test_a_briefing_the_user_asked_for_is_not_queued_behind_fetched_orders(self, owner, case):
        fetched = _job(owner, document_type="court_order")
        briefing = _job(owner, job_type="case_briefing", case=case)

        assert Command()._claim_next_job().id == briefing.id
        assert Command()._claim_next_job().id == fetched.id

    def test_same_tier_stays_first_in_first_out(self, owner):
        first = _job(owner)
        second = _job(owner)

        assert Command()._claim_next_job().id == first.id
        assert Command()._claim_next_job().id == second.id

    def test_claiming_marks_the_job_running_and_an_empty_queue_returns_none(self, owner):
        job = _job(owner)
        claimed = Command()._claim_next_job()
        job.refresh_from_db()
        assert (claimed.id, job.status, job.attempts) == (job.id, "running", 1)
        assert Command()._claim_next_job() is None


@pytest.mark.django_db
class TestInteractiveLane:
    def test_never_claims_the_long_portal_jobs(self, owner, case):
        for job_type in ("advocate_search", "advocate_import", "tracking_refresh"):
            _job(owner, job_type=job_type)
        _job(owner, job_type="order_sync", case=case)

        assert Command()._claim_next_job("interactive") is None

    def test_still_serves_uploads_and_briefings_while_bulk_jobs_are_waiting(self, owner, case):
        _job(owner, job_type="advocate_search")  # oldest
        upload = _job(owner)
        briefing = _job(owner, job_type="case_briefing", case=case)

        got = {Command()._claim_next_job("interactive").id for _ in range(2)}

        assert got == {upload.id, briefing.id}

    def test_the_default_lane_still_drains_everything(self, owner):
        search = _job(owner, job_type="advocate_search")
        assert Command()._claim_next_job().id == search.id

    def test_the_command_accepts_and_reports_the_lane(self, owner):
        out = StringIO()
        with patch.object(Command, "_process_job"), patch(
            "core.management.commands.process_jobs.close_old_connections"
        ):
            call_command("process_jobs", "--once", "--lane", "interactive",
                         "--max-jobs", "0", "--max-rss-mb", "0", stdout=out)
        assert "lane=interactive" in out.getvalue()
