"""The dashboard's "Refresh all tracked cases" (core/services/bulk_refresh.py).

refresh_case_tracking itself is patched out everywhere here -- its own
behaviour is covered elsewhere; what matters is the fan-out around it:
batching into follow-on jobs, the system-wide single-run cap, stopping on
a portal outage, cancel, and the one-fetch-per-hour limit being honoured.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Case, ProcessingJob
from core.services import bulk_refresh
from core.services.court_data import CaptchaSolveError, CaseNotFoundError

REFRESH = "core.services.court_tracking.refresh_case_tracking"


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="bulk-advocate", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="bulk-other", password="pw-12345")


def _api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _tracked(owner, n, **extra):
    return [
        Case.objects.create(
            owner=owner,
            case_number=f"{owner.username}/{i}",
            title=f"Case {i}",
            client_name="C",
            court_type="district",
            tracking_config={"court_type": "district", "cnr": f"TSHY01{i:010d}"},
            tracking_enabled=True,
            **extra,
        )
        for i in range(n)
    ]


def _ok(case, force=False):
    return {"rate_limited": False, "new_hearing_dates": [], "client_update_drafts": 0}


def _drain(job):
    """Run the job and every follow-on it queues, like the worker would."""
    jobs = [job]
    while True:
        job.refresh_from_db()
        bulk_refresh.run_tracking_refresh(job)
        job.refresh_from_db()
        next_id = (job.payload or {}).get("next_job_id")
        if not next_id:
            return jobs
        job = ProcessingJob.objects.get(id=next_id)
        jobs.append(job)


@pytest.mark.django_db
class TestStarting:
    def test_nothing_tracked(self, advocate):
        _tracked(advocate, 1, status="closed")
        Case.objects.create(owner=advocate, case_number="U/1", title="Untracked", client_name="C")
        resp = _api(advocate).post("/api/cases/refresh-all/")
        assert resp.status_code == 400
        assert resp.data["code"] == "nothing_to_refresh"

    def test_starts_a_run_over_open_tracked_cases_oldest_first(self, advocate):
        fresh, stale = _tracked(advocate, 2)
        Case.objects.filter(id=fresh.id).update(last_fetched_at=timezone.now())
        resp = _api(advocate).post("/api/cases/refresh-all/")
        assert resp.status_code == 202, resp.data
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.job_type == "tracking_refresh"
        assert job.payload["case_ids"] == [stale.id, fresh.id]
        assert resp.data["total"] == 2

    def test_only_one_run_system_wide_and_no_job_id_leak(self, advocate, other):
        _tracked(advocate, 1)
        _tracked(other, 1)
        first = _api(advocate).post("/api/cases/refresh-all/")
        again = _api(advocate).post("/api/cases/refresh-all/")
        theirs = _api(other).post("/api/cases/refresh-all/")

        assert first.status_code == 202
        assert again.status_code == 409
        assert again.data["job_id"] == first.data["job_id"]  # your own run
        assert theirs.status_code == 409
        assert "job_id" not in theirs.data  # never someone else's

    def test_get_returns_the_latest_run(self, advocate):
        _tracked(advocate, 1)
        assert _api(advocate).get("/api/cases/refresh-all/").data == {"job_id": None}
        started = _api(advocate).post("/api/cases/refresh-all/").data
        assert _api(advocate).get("/api/cases/refresh-all/").data["job_id"] == started["job_id"]


@pytest.mark.django_db
class TestRunning:
    def test_batches_into_follow_on_jobs_with_cumulative_totals(self, advocate):
        cases = _tracked(advocate, bulk_refresh.BATCH_SIZE + 3)
        job = bulk_refresh.start_bulk_refresh(advocate)
        with patch(REFRESH, side_effect=_ok) as refresh:
            jobs = _drain(job)

        assert len(jobs) == 2
        assert refresh.call_count == len(cases)
        status = bulk_refresh.run_status(job)
        assert status["current_job_id"] == jobs[-1].id
        assert status["done"] == status["total"] == len(cases)
        assert status["results"]["refreshed"] == len(cases)
        assert jobs[1].payload["root_job_id"] == job.id

    def test_rate_limited_cases_are_counted_not_refetched(self, advocate):
        _tracked(advocate, 2)
        job = bulk_refresh.start_bulk_refresh(advocate)
        with patch(REFRESH, return_value={"rate_limited": True}):
            _drain(job)
        assert bulk_refresh.run_status(job)["results"]["rate_limited"] == 2

    def test_counts_new_dates_and_drafts(self, advocate):
        _tracked(advocate, 1)
        job = bulk_refresh.start_bulk_refresh(advocate)
        outcome = {"rate_limited": False, "new_hearing_dates": ["d1", "d2"], "client_update_drafts": 1}
        with patch(REFRESH, return_value=outcome):
            _drain(job)
        results = bulk_refresh.run_status(job)["results"]
        assert results["new_hearing_dates"] == 2
        assert results["drafts_created"] == 1

    def test_stops_after_consecutive_portal_errors(self, advocate):
        _tracked(advocate, 8)
        job = bulk_refresh.start_bulk_refresh(advocate)
        with patch(REFRESH, side_effect=CaptchaSolveError("portal down")) as refresh:
            _drain(job)
        assert refresh.call_count == bulk_refresh.MAX_CONSECUTIVE_PORTAL_ERRORS
        status = bulk_refresh.run_status(job)
        assert "portal errors in a row" in status["aborted_reason"]
        assert status["results"]["failed"] == bulk_refresh.MAX_CONSECUTIVE_PORTAL_ERRORS
        job.refresh_from_db()
        assert len(job.payload["case_ids"]) == 3  # the rest were never touched

    def test_a_not_found_case_is_not_an_outage(self, advocate):
        _tracked(advocate, 7)
        job = bulk_refresh.start_bulk_refresh(advocate)
        effects = [CaptchaSolveError("x")] * 4 + [CaseNotFoundError("gone")] + [CaptchaSolveError("x")] * 2
        with patch(REFRESH, side_effect=effects) as refresh:
            _drain(job)
        assert refresh.call_count == 7
        assert bulk_refresh.run_status(job)["aborted_reason"] == ""

    def test_one_unexpected_error_does_not_end_the_run(self, advocate):
        _tracked(advocate, 3)
        job = bulk_refresh.start_bulk_refresh(advocate)
        with patch(REFRESH, side_effect=[RuntimeError("bug"), _ok(None), _ok(None)]):
            _drain(job)
        results = bulk_refresh.run_status(job)["results"]
        assert results["failed"] == 1
        assert results["refreshed"] == 2

    def test_cancel_stops_before_the_next_case(self, advocate):
        _tracked(advocate, 4)
        job = bulk_refresh.start_bulk_refresh(advocate)
        ProcessingJob.objects.filter(id=job.id).update(status="running")
        job.refresh_from_db()

        def refresh_then_cancel(case, force=False):
            bulk_refresh.cancel_run(job)
            return _ok(case)

        with patch(REFRESH, side_effect=refresh_then_cancel) as refresh:
            with pytest.raises(bulk_refresh.BulkRefreshCancelled):
                bulk_refresh.run_tracking_refresh(job)
        assert refresh.call_count == 1
        job.refresh_from_db()
        assert len(job.payload["case_ids"]) == 3
        assert job.payload["aborted_reason"] == "Cancelled."

    def test_a_case_deleted_meanwhile_is_skipped(self, advocate):
        cases = _tracked(advocate, 2)
        job = bulk_refresh.start_bulk_refresh(advocate)
        cases[0].delete()
        with patch(REFRESH, side_effect=_ok):
            _drain(job)
        results = bulk_refresh.run_status(job)["results"]
        assert results["skipped"] == 1
        assert results["refreshed"] == 1


@pytest.mark.django_db
class TestIsolation:
    def test_another_advocate_cannot_read_or_cancel_a_run(self, advocate, other):
        _tracked(advocate, 1)
        job_id = _api(advocate).post("/api/cases/refresh-all/").data["job_id"]
        assert _api(other).get(f"/api/cases/refresh-all/{job_id}/").status_code == 404
        assert _api(other).post(f"/api/cases/refresh-all/{job_id}/cancel/").status_code == 404
        assert not ProcessingJob.objects.get(id=job_id).cancel_requested
        assert _api(other).get("/api/cases/refresh-all/").data == {"job_id": None}

    def test_a_run_only_touches_its_owners_cases(self, advocate, other):
        _tracked(advocate, 1)
        (theirs,) = _tracked(other, 1)
        job = bulk_refresh.start_bulk_refresh(advocate)
        job.payload["case_ids"].append(theirs.id)  # a forged payload
        job.save()
        with patch(REFRESH, side_effect=_ok) as refresh:
            _drain(job)
        refreshed = {call.args[0].id for call in refresh.call_args_list}
        assert theirs.id not in refreshed
