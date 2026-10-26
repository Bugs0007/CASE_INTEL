"""Order sync results: what a sync records, and how a failed download behaves.

Driven with a fake provider over the captured District Courts page (so the
listing is the real parser's output) -- no live portal, no real storage.
"""

from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User

from core.management.commands.process_jobs import Command as ProcessJobsCommand
from core.models import Case, CourtOrder, Document, ProcessingJob
from core.services.court_data import CaptchaSolveError, CaseNotFoundError, CourtPortalError
from core.services.court_data.ecourts_parsing import _parse_district_orders
from core.services.court_order_sync import (
    MAX_CONSECUTIVE_PORTAL_FAILURES,
    MAX_DOWNLOADS_PER_SYNC,
    MAX_TOTAL_DOWNLOAD_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    error_kind,
    sync_case_orders,
)

PAGE = (
    Path(__file__).parent
    / "fixtures/causelists/district_ecourts/cnr_case_page/TSHC010030082026.html"
)
CNR = "TSHC010030082026"
PDF = b"%PDF-1.7 fake order"


def _numbered_page(count: int) -> str:
    """The captured page with `count` interim orders (numbers 1..count, each a
    day apart) instead of its single one."""
    html = PAGE.read_text(encoding="utf-8")
    start = html.index("<tr><td>&nbsp;&nbsp;1</td>")
    end = html.index("</tr>", start) + len("</tr>")
    row = html[start:end]
    rows = "".join(
        row.replace("&nbsp;&nbsp;1</td>", f"&nbsp;&nbsp;{n}</td>").replace("15-09-2026", f"{n:02d}-09-2026")
        for n in range(1, count + 1)
    )
    return html[:start] + rows + html[end:]


def _listing(count: int):
    return [r for r, _ in _parse_district_orders(_numbered_page(count), CNR)]


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="sync-advocate", password="pw-12345")


@pytest.fixture
def case(advocate):
    return Case.objects.create(
        owner=advocate, case_number="OS/336/2026", title="A vs B", client_name="A",
        cnr_number=CNR, court_type="district", tracking_enabled=True,
        tracking_config={"court_type": "district", "cnr": CNR},
    )


class FakePortal:
    """list_orders returns the parsed page; download_order plays a script of
    outcomes per call: bytes -> success, an exception instance -> raised."""

    def __init__(self, count, script=None):
        self.records = _listing(count)
        self.script = list(script or [])
        self.downloads = []
        self.provider = MagicMock()
        self.provider.list_orders.side_effect = lambda config: list(self.records)
        self.provider.download_order.side_effect = self._download

    def _download(self, config, record):
        self.downloads.append(record.dedup_key)
        outcome = self.script.pop(0) if self.script else PDF
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def sleeps():
    with patch("core.services.court_order_sync.time.sleep") as sleep:
        yield sleep


def run_sync(case, portal):
    with patch("core.services.court_order_sync.get_provider", return_value=portal.provider), \
            patch("core.services.court_order_sync.default_storage") as storage:
        storage.save.side_effect = lambda name, content: name
        return sync_case_orders(case)


@pytest.mark.django_db
class TestResultCounts:
    def test_a_clean_sync_reports_everything_downloaded(self, case, sleeps):
        result = run_sync(case, FakePortal(2))
        assert result["listed"] == result["new"] == result["downloaded"] == 2
        assert (result["failed"], result["pending"], result["stopped_early"]) == (0, 0, False)
        rows = CourtOrder.objects.filter(case=case)
        assert {r.download_status for r in rows} == {"downloaded"}
        assert all(r.document_id for r in rows)

    def test_nothing_listed_is_a_clean_zero(self, case, sleeps):
        result = run_sync(case, FakePortal(0))
        assert result == {
            "listed": 0, "new": 0, "downloaded": 0, "failed": 0, "pending": 0,
            "relabelled": 0, "stopped_early": False, "reason": "",
        }

    def test_orders_beyond_the_per_sync_cap_are_saved_pending_and_finished_next_sync(self, case, sleeps):
        portal = FakePortal(MAX_DOWNLOADS_PER_SYNC + 2)
        first = run_sync(case, portal)
        assert (first["new"], first["downloaded"], first["pending"]) == (
            MAX_DOWNLOADS_PER_SYNC + 2, MAX_DOWNLOADS_PER_SYNC, 2,
        )
        second = run_sync(case, portal)
        assert (second["new"], second["downloaded"], second["pending"]) == (0, 2, 0)
        assert CourtOrder.objects.filter(case=case).count() == MAX_DOWNLOADS_PER_SYNC + 2
        assert len(set(portal.downloads)) == len(portal.downloads)  # nothing fetched twice


@pytest.mark.django_db
class TestRetriesAndPending:
    def test_transient_error_is_retried_with_backoff_then_succeeds(self, case, sleeps):
        portal = FakePortal(1, script=[CaptchaSolveError("OCR failed"), CourtPortalError("503"), PDF])
        result = run_sync(case, portal)
        assert (result["downloaded"], result["failed"]) == (1, 0)
        assert len(portal.downloads) == 3
        waits = [c.args[0] for c in sleeps.call_args_list]
        assert waits == list(RETRY_BACKOFF_SECONDS)  # 5 s then 15 s
        (row,) = CourtOrder.objects.filter(case=case)
        assert row.download_status == "downloaded" and row.document_id

    def test_a_dropped_connection_counts_as_transient(self, case, sleeps):
        portal = FakePortal(1, script=[ConnectionResetError("server disconnected"), PDF])
        assert run_sync(case, portal)["downloaded"] == 1
        assert len(portal.downloads) == 2

    def test_no_longer_listed_is_not_retried(self, case, sleeps):
        portal = FakePortal(1, script=[CaseNotFoundError("gone")])
        result = run_sync(case, portal)
        assert (result["failed"], result["pending"]) == (1, 1)
        assert len(portal.downloads) == 1
        assert [c.args[0] for c in sleeps.call_args_list] == []

    def test_exhausted_retries_leave_a_pending_row_and_no_document(self, case, sleeps):
        portal = FakePortal(1, script=[CaptchaSolveError("Invalid Captcha")] * 3)
        result = run_sync(case, portal)
        assert len(portal.downloads) == 3  # one try + two retries
        assert (result["downloaded"], result["failed"], result["pending"]) == (0, 1, 1)
        assert result["reason"] == "captcha"
        (row,) = CourtOrder.objects.filter(case=case)
        assert row.download_status == "pending" and row.document_id is None
        assert row.download_attempts == 1 and "Invalid Captcha" in row.last_download_error
        assert Document.objects.filter(case=case).count() == 0

    def test_the_pending_row_is_completed_in_place_by_the_next_sync(self, case, sleeps):
        portal = FakePortal(1, script=[CourtPortalError("down")] * 3)
        run_sync(case, portal)
        (row,) = CourtOrder.objects.filter(case=case)
        first_id = row.id

        again = run_sync(case, portal)  # script exhausted -> downloads succeed
        assert (again["new"], again["downloaded"], again["pending"]) == (0, 1, 0)
        row.refresh_from_db()
        assert row.id == first_id and CourtOrder.objects.filter(case=case).count() == 1
        assert row.download_status == "downloaded" and row.document_id
        assert row.download_attempts == 2 and row.last_download_error == ""
        assert Document.objects.filter(case=case).count() == 1

    def test_a_third_sync_after_success_changes_nothing(self, case, sleeps):
        portal = FakePortal(2)
        run_sync(case, portal)
        before = (CourtOrder.objects.count(), Document.objects.count(), len(portal.downloads))
        result = run_sync(case, portal)
        assert (result["new"], result["downloaded"]) == (0, 0)
        assert (CourtOrder.objects.count(), Document.objects.count(), len(portal.downloads)) == before

    def test_two_orders_failing_in_a_row_stop_the_sync(self, case, sleeps):
        script = [CourtPortalError("down")] * (3 * MAX_CONSECUTIVE_PORTAL_FAILURES)
        portal = FakePortal(4, script=script)
        result = run_sync(case, portal)
        assert result["stopped_early"] is True
        assert result["failed"] == MAX_CONSECUTIVE_PORTAL_FAILURES
        assert len(portal.downloads) == 3 * MAX_CONSECUTIVE_PORTAL_FAILURES  # the other two untouched
        assert result["pending"] == 4
        assert CourtOrder.objects.filter(case=case, download_attempts=0).count() == 2

    def test_a_success_between_failures_resets_the_streak(self, case, sleeps):
        script = [CourtPortalError("x")] * 3 + [PDF] + [CourtPortalError("x")] * 3
        result = run_sync(case, FakePortal(3, script=script))
        assert result["stopped_early"] is False
        assert (result["downloaded"], result["failed"]) == (1, 2)

    def test_giving_up_after_the_total_attempt_cap(self, case, sleeps):
        portal = FakePortal(1)
        portal.script = [CourtPortalError("x")] * (3 * MAX_TOTAL_DOWNLOAD_ATTEMPTS)
        for _ in range(MAX_TOTAL_DOWNLOAD_ATTEMPTS):
            run_sync(case, portal)
        (row,) = CourtOrder.objects.filter(case=case)
        assert row.download_status == "failed" and row.download_attempts == MAX_TOTAL_DOWNLOAD_ATTEMPTS
        calls = len(portal.downloads)
        run_sync(case, portal)  # failed rows are left alone
        assert len(portal.downloads) == calls

    def test_a_pending_order_the_portal_stopped_listing_is_marked_failed(self, case, sleeps):
        portal = FakePortal(1, script=[CourtPortalError("x")] * 3)
        run_sync(case, portal)
        portal.records = []
        result = run_sync(case, portal)
        (row,) = CourtOrder.objects.filter(case=case)
        assert row.download_status == "failed" and "No longer listed" in row.last_download_error
        assert result["pending"] == 0


@pytest.mark.django_db
class TestFinalVersusInterim:
    def test_same_number_and_date_are_two_orders(self, case, sleeps):
        interim = _listing(1)[0]
        final = type(interim)(
            cnr=CNR, order_number="1", order_date=interim.order_date, section="final",
            description="Final order 1",
        )
        portal = FakePortal(0)
        portal.records = [interim, final]
        result = run_sync(case, portal)
        assert result["downloaded"] == 2
        keys = set(CourtOrder.objects.filter(case=case).values_list("dedup_key", flat=True))
        assert keys == {interim.dedup_key, final.dedup_key} and len(keys) == 2

    def test_a_legacy_row_for_a_final_order_is_relabelled_not_fetched_again(self, case, sleeps):
        """Saved before sections existed: key without ':final'. The portal now
        lists it as final -- same number and date -- so it is the same order."""
        interim = _listing(1)[0]
        legacy_key = interim.dedup_key
        held = CourtOrder.objects.create(
            owner=case.owner, case=case, order_number="1", order_date=interim.order_date,
            dedup_key=legacy_key, download_status="downloaded",
        )
        final = type(interim)(cnr=CNR, order_number="1", order_date=interim.order_date, section="final")
        portal = FakePortal(0)
        portal.records = [final]
        result = run_sync(case, portal)
        assert (result["relabelled"], result["downloaded"]) == (1, 0)
        held.refresh_from_db()
        assert held.dedup_key == final.dedup_key and CourtOrder.objects.filter(case=case).count() == 1
        assert portal.downloads == []


class TestErrorKind:
    def test_mapped_labels_only(self):
        assert error_kind(CaptchaSolveError("whatever")) == "captcha"
        assert error_kind(CourtPortalError("whatever")) == "portal"
        assert error_kind(ConnectionResetError("x")) == "portal"
        assert error_kind("Invalid Captcha after 3 attempts") == "captcha"
        assert error_kind("OCR failed to read the CAPTCHA image.") == "captcha"
        assert error_kind("Server disconnected without sending a response") == "portal"
        assert error_kind("unrecognized portal response") == "portal"
        assert error_kind("ValueError: bad thing") == "other"
        assert error_kind("") == "other"


@pytest.mark.django_db
class TestJobRecordsTheResult:
    def _run_job(self, case, portal):
        job, _ = ProcessingJob.enqueue_order_sync(case)
        with patch("core.services.court_order_sync.get_provider", return_value=portal.provider), \
                patch("core.services.court_order_sync.default_storage") as storage, \
                patch("core.services.court_order_sync.time.sleep"):
            storage.save.side_effect = lambda name, content: name
            ProcessJobsCommand(stdout=StringIO())._process_job(job, processor=None)
        job.refresh_from_db()
        return job

    def test_clean_run_is_succeeded_with_the_result_stored(self, case):
        job = self._run_job(case, FakePortal(2))
        assert job.status == "succeeded" and job.error == ""
        assert job.payload["result"]["downloaded"] == 2
        assert set(job.payload["result"]) >= {"listed", "new", "downloaded", "failed", "pending"}

    def test_run_with_a_failed_download_ends_partial_not_succeeded(self, case):
        raw = CourtPortalError("RAW-PORTAL-TEXT")
        portal = FakePortal(2, script=[PDF, raw, raw, raw])
        job = self._run_job(case, portal)
        assert job.status == "partial"
        result = job.payload["result"]
        assert (result["failed"], result["downloaded"], result["pending"]) == (1, 1, 1)
        assert "could not be downloaded" in job.error
        assert "RAW-PORTAL-TEXT" not in job.error  # never the portal's own words

    def test_zero_orders_listed_is_succeeded(self, case):
        job = self._run_job(case, FakePortal(0))
        assert job.status == "succeeded" and job.payload["result"]["listed"] == 0

    def test_a_listing_that_never_came_back_is_failed(self, case):
        portal = FakePortal(1)
        portal.provider.list_orders.side_effect = CaptchaSolveError("Invalid Captcha after 3 attempts")
        job = self._run_job(case, portal)
        assert job.status == "failed" and "Invalid Captcha" in job.error
        assert "result" not in (job.payload or {})

    def test_a_failed_listing_does_not_block_the_next_refresh_from_queueing_a_sync(self, case):
        portal = FakePortal(1)
        portal.provider.list_orders.side_effect = CaptchaSolveError("x")
        first = self._run_job(case, portal)
        assert first.status == "failed"
        retry, created = ProcessingJob.enqueue_order_sync(case)
        assert created and retry.id != first.id and retry.status == "queued"
