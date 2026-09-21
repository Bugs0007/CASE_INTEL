"""
Advocate search + bulk import tests.

Mocks at the same boundary the rest of the codebase already treats as
authoritative: core.services.court_data.get_provider() (see base.py's
"CourtDataProvider is the ONLY interface the rest of Case Intel talks to"
docstring), plus a couple of pure unit tests for split_bar_code. No live
eCourts calls.

The advocate SEARCH is now an async, state-wide fan-out (job_type=
"advocate_search"): the view enqueues a ProcessingJob, the worker runs
core.services.advocate_search.run_advocate_search which loops over every
district and court complex in the state. The IMPORT stays a separate async
job (job_type="advocate_import").
"""

import asyncio
import dataclasses
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bharat_courts import CaseInfo
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import AdvocateSearchPreference, Case, JobAlreadyRunningError, ProcessingJob
from core.services.advocate_import import run_advocate_import
from core.services.advocate_search import AdvocateSearchCancelled, run_advocate_search
from core.services.court_data import CaptchaSolveError, CourtPortalError
from core.services.court_tracking import build_case_title, opposing_party_for_role
from bharat_courts.districtcourts.parser import ServerError as DistrictServerError
from core.services.court_data.ecourts_parsing import split_bar_code
from core.services.court_data.ecourts_provider import _TokenSeedingDistrictClient
from core.services.court_data.models import CourtCaseData


# ---------------------------------------------------------------------------
# split_bar_code (pure function)
# ---------------------------------------------------------------------------


class TestSplitBarCode:
    def test_valid_format(self):
        assert split_bar_code("MAH/1234/2015") == ("MAH", "1234", "2015")

    def test_lowercase_state_is_uppercased(self):
        assert split_bar_code("mah/1234/2015") == ("MAH", "1234", "2015")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            split_bar_code("not-a-bar-code")

    def test_missing_year_raises(self):
        with pytest.raises(ValueError):
            split_bar_code("MAH/1234")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def user_a():
    return User.objects.create_user(username="alice", password="alice-pass-123")


@pytest.fixture
def user_b():
    return User.objects.create_user(username="bob", password="bob-pass-123")


def _authed_client(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def client_a(user_a):
    return _authed_client(user_a)


@pytest.fixture
def client_b(user_b):
    return _authed_client(user_b)


def _ci(cnr: str, **overrides) -> CaseInfo:
    defaults = dict(
        case_number="123/2024",
        case_type="Civil Suit",
        cnr_number=cnr,
        petitioner="Suresh Kumar",
        respondent="State Bank",
        status="Pending",
        court_name="Civil Court",
    )
    defaults.update(overrides)
    return CaseInfo(**defaults)


# ---------------------------------------------------------------------------
# AdvocateSearchView (async enqueue, state-only)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdvocateSearchView:
    def test_valid_name_search_enqueues_job(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "1"},
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.job_type == "advocate_search"
        assert job.payload["advocate_name"] == "Suresh"
        assert job.payload["bar_code"] == ""
        assert job.payload["state_code"] == "1"
        assert job.payload["status_filter"] == "Both"

    def test_valid_bar_code_search(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "MAH/1234/2015", "court_type": "district", "state_code": "1"},
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.payload["bar_code"] == "MAH/1234/2015"
        assert job.payload["advocate_name"] == ""

    def test_dist_code_sets_districts_filter_for_single_district_search(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "1", "dist_code": "26"},
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.payload["districts_filter"] == ["26"]

    def test_omitting_dist_code_means_state_wide(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "1"},
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert (job.payload or {}).get("districts_filter") is None

    def test_name_too_short_rejected(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "AB", "court_type": "district", "state_code": "1"},
            format="json",
        )
        assert resp.status_code == 400

    def test_missing_state_rejected(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district"},
            format="json",
        )
        assert resp.status_code == 400

    def test_invalid_status_filter_rejected(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "1", "status_filter": "Nonsense"},
            format="json",
        )
        assert resp.status_code == 400

    def test_high_court_not_yet_supported(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "high_court", "state_code": "1"},
            format="json",
        )
        assert resp.status_code == 400

    def test_search_saves_state_preference(self, client_a, user_a):
        client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "7"},
            format="json",
        )
        pref = AdvocateSearchPreference.objects.get(owner=user_a)
        assert pref.hierarchy_config == {"state_code": "7"}

    def test_requires_authentication(self):
        anon = APIClient()
        resp = anon.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "1"},
            format="json",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# AdvocateSearchStatusView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdvocateSearchStatusView:
    def test_running_job_returns_progress_without_results(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="running",
            progress_current=3, progress_total=30, payload={"state_code": "1"},
        )
        resp = client_a.get(f"/api/cases/search-advocate/{job.id}/")
        assert resp.status_code == 200
        assert resp.data["status"] == "running"
        assert resp.data["progress_current"] == 3
        assert resp.data["progress_total"] == 30
        assert resp.data["results"] == []

    def test_succeeded_job_returns_results_and_failures(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="succeeded",
            payload={
                "results": [{"cnr_number": "X1"}, {"cnr_number": "X2"}],
                "failures": [{"district": "Pune", "court_complex": "CX", "error": "captcha"}],
                "districts_total": 30, "complexes_searched": 88,
                "districts_status": {"1": {"name": "Pune", "status": "success", "complexes_total": 3, "complexes_ok": 3, "complexes_failed": 0}},
            },
        )
        resp = client_a.get(f"/api/cases/search-advocate/{job.id}/")
        assert resp.status_code == 200
        assert resp.data["status"] == "succeeded"
        assert len(resp.data["results"]) == 2
        assert len(resp.data["failures"]) == 1
        assert resp.data["districts_total"] == 30
        assert resp.data["districts_status"]["1"]["status"] == "success"

    def test_running_job_with_no_districts_status_yet_returns_empty_dict(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="running", payload={"state_code": "1"},
        )
        resp = client_a.get(f"/api/cases/search-advocate/{job.id}/")
        assert resp.status_code == 200
        assert resp.data["districts_status"] == {}

    def test_failed_job_surfaces_error_not_500(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="failed",
            error="Could not list districts", payload={"state_code": "1"},
        )
        resp = client_a.get(f"/api/cases/search-advocate/{job.id}/")
        assert resp.status_code == 200
        assert resp.data["status"] == "failed"
        assert "district" in resp.data["error"].lower()

    def test_other_users_search_job_not_visible(self, client_a, user_b):
        job = ProcessingJob.objects.create(owner=user_b, job_type="advocate_search", payload={})
        resp = client_a.get(f"/api/cases/search-advocate/{job.id}/")
        assert resp.status_code == 404

    def test_wrong_job_type_not_returned_by_search_status(self, client_a, user_a):
        # An import job id must not resolve on the search-status endpoint.
        job = ProcessingJob.objects.create(owner=user_a, job_type="advocate_import", payload={})
        resp = client_a.get(f"/api/cases/search-advocate/{job.id}/")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AdvocateSearchRetryFailedView
# ---------------------------------------------------------------------------


def _completed_job(user, *, districts_status, results=None, **payload_overrides):
    payload = {
        "state_code": "1", "court_type": "district", "advocate_name": "Suresh",
        "bar_code": "", "status_filter": "Both",
        "results": results or [], "failures": [], "districts_total": len(districts_status),
        "districts_status": districts_status, "complexes_searched": 0,
    }
    payload.update(payload_overrides)
    return ProcessingJob.objects.create(
        owner=user, job_type="advocate_search", status="succeeded", payload=payload,
    )


@pytest.mark.django_db
class TestAdvocateSearchRetryFailedView:
    def test_enqueues_new_job_scoped_to_failed_districts_only(self, client_a, user_a):
        original = _completed_job(
            user_a,
            results=[{"cnr_number": "OLD1"}],
            districts_status={
                "1": {"name": "Dist A", "status": "success", "complexes_total": 2, "complexes_ok": 2, "complexes_failed": 0},
                "2": {"name": "Dist B", "status": "failed", "complexes_total": 2, "complexes_ok": 0, "complexes_failed": 2},
            },
        )
        resp = client_a.post(f"/api/cases/search-advocate/{original.id}/retry-failed/")
        assert resp.status_code == 202
        new_job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert new_job.id != original.id
        assert new_job.payload["districts_filter"] == ["2"]
        assert new_job.payload["seed_results"] == [{"cnr_number": "OLD1"}]
        assert new_job.payload["seed_districts_status"] == {
            "1": {"name": "Dist A", "status": "success", "complexes_total": 2, "complexes_ok": 2, "complexes_failed": 0},
        }
        assert new_job.payload["retry_of"] == original.id
        # Search params carried forward from the original job.
        assert new_job.payload["state_code"] == "1"
        assert new_job.payload["advocate_name"] == "Suresh"

    def test_partial_districts_are_also_retried(self, client_a, user_a):
        original = _completed_job(
            user_a,
            districts_status={
                "1": {"name": "Dist A", "status": "partial", "complexes_total": 2, "complexes_ok": 1, "complexes_failed": 1},
            },
        )
        resp = client_a.post(f"/api/cases/search-advocate/{original.id}/retry-failed/")
        assert resp.status_code == 202
        new_job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert new_job.payload["districts_filter"] == ["1"]

    def test_nothing_to_retry_when_everything_succeeded(self, client_a, user_a):
        original = _completed_job(
            user_a,
            districts_status={
                "1": {"name": "Dist A", "status": "success", "complexes_total": 2, "complexes_ok": 2, "complexes_failed": 0},
            },
        )
        resp = client_a.post(f"/api/cases/search-advocate/{original.id}/retry-failed/")
        assert resp.status_code == 400

    def test_cannot_retry_a_still_running_job(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="running", payload={"state_code": "1"},
        )
        resp = client_a.post(f"/api/cases/search-advocate/{job.id}/retry-failed/")
        assert resp.status_code == 400

    def test_other_users_job_not_retryable(self, client_a, user_b):
        original = _completed_job(
            user_b,
            districts_status={
                "1": {"name": "Dist A", "status": "failed", "complexes_total": 1, "complexes_ok": 0, "complexes_failed": 1},
            },
        )
        resp = client_a.post(f"/api/cases/search-advocate/{original.id}/retry-failed/")
        assert resp.status_code == 404

    def test_blocked_by_concurrency_cap(self, client_a, user_a):
        original = _completed_job(
            user_a,
            districts_status={
                "1": {"name": "Dist A", "status": "failed", "complexes_total": 1, "complexes_ok": 0, "complexes_failed": 1},
            },
        )
        # Another advocate_search is already running system-wide.
        ProcessingJob.objects.create(owner=user_a, job_type="advocate_search", status="running", payload={})
        resp = client_a.post(f"/api/cases/search-advocate/{original.id}/retry-failed/")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# AdvocateSearchCancelView / AdvocateSearchActiveListView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdvocateSearchCancelView:
    def test_cancel_queued_job_is_immediate(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="queued", payload={"state_code": "1"},
        )
        resp = client_a.post(f"/api/cases/search-advocate/{job.id}/cancel/")
        assert resp.status_code == 200
        assert resp.data["status"] == "cancelled"
        job.refresh_from_db()
        assert job.status == "cancelled"
        assert job.finished_at is not None

    def test_cancel_running_job_flags_but_does_not_finish_it(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="running", payload={"state_code": "1"},
        )
        resp = client_a.post(f"/api/cases/search-advocate/{job.id}/cancel/")
        assert resp.status_code == 200
        assert resp.data["status"] == "running"
        assert resp.data["cancel_requested"] is True
        job.refresh_from_db()
        assert job.status == "running"
        assert job.cancel_requested is True

    def test_cancelling_a_queued_job_clears_the_concurrency_cap(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="queued", payload={"state_code": "1"},
        )
        client_a.post(f"/api/cases/search-advocate/{job.id}/cancel/")
        # A cancelled job must not still count as "active" for the
        # system-wide single-in-flight cap -- otherwise cancelling would
        # be a no-op from the user's perspective (still blocked).
        resp = client_a.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json")
        assert resp.status_code == 202

    def test_cancel_already_finished_job_rejected(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="succeeded", payload={},
        )
        resp = client_a.post(f"/api/cases/search-advocate/{job.id}/cancel/")
        assert resp.status_code == 400
        job.refresh_from_db()
        assert job.status == "succeeded"

    def test_cannot_cancel_other_users_job(self, client_a, user_b):
        job = ProcessingJob.objects.create(
            owner=user_b, job_type="advocate_search", status="running", payload={},
        )
        resp = client_a.post(f"/api/cases/search-advocate/{job.id}/cancel/")
        assert resp.status_code == 404
        job.refresh_from_db()
        assert job.cancel_requested is False

    def test_cannot_cancel_an_import_job_via_this_endpoint(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_import", status="running", payload={},
        )
        resp = client_a.post(f"/api/cases/search-advocate/{job.id}/cancel/")
        assert resp.status_code == 404

    def test_cancel_nonexistent_job_404(self, client_a):
        resp = client_a.post("/api/cases/search-advocate/999999/cancel/")
        assert resp.status_code == 404

    def test_requires_authentication(self):
        anon = APIClient()
        resp = anon.post("/api/cases/search-advocate/1/cancel/")
        assert resp.status_code == 401


@pytest.mark.django_db
class TestAdvocateSearchActiveListView:
    def test_lists_own_queued_and_running_searches(self, client_a, user_a):
        running = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="running",
            progress_current=2, progress_total=10,
            payload={"state_code": "1", "advocate_name": "Suresh", "results": [{"cnr_number": "X1"}]},
        )
        queued = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="queued", payload={"state_code": "2"},
        )
        resp = client_a.get("/api/cases/search-advocate/active/")
        assert resp.status_code == 200
        ids = {row["job_id"] for row in resp.data}
        assert ids == {running.id, queued.id}
        running_row = next(row for row in resp.data if row["job_id"] == running.id)
        assert running_row["progress_current"] == 2
        assert running_row["progress_total"] == 10
        assert running_row["advocate_name"] == "Suresh"
        assert running_row["results_total"] == 1

    def test_excludes_terminal_jobs(self, client_a, user_a):
        for terminal_status in ("succeeded", "failed", "cancelled"):
            ProcessingJob.objects.create(
                owner=user_a, job_type="advocate_search", status=terminal_status, payload={},
            )
        resp = client_a.get("/api/cases/search-advocate/active/")
        assert resp.status_code == 200
        assert resp.data == []

    def test_excludes_other_users_searches(self, client_a, user_b):
        ProcessingJob.objects.create(owner=user_b, job_type="advocate_search", status="running", payload={})
        resp = client_a.get("/api/cases/search-advocate/active/")
        assert resp.status_code == 200
        assert resp.data == []

    def test_excludes_other_job_types(self, client_a, user_a):
        ProcessingJob.objects.create(owner=user_a, job_type="advocate_import", status="running", payload={})
        resp = client_a.get("/api/cases/search-advocate/active/")
        assert resp.status_code == 200
        assert resp.data == []

    def test_requires_authentication(self):
        anon = APIClient()
        resp = anon.get("/api/cases/search-advocate/active/")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# run_advocate_search (state-wide fan-out service)
# ---------------------------------------------------------------------------


def _search_job(user, **overrides):
    params = {
        "state_code": "1", "court_type": "district",
        "advocate_name": "Suresh", "bar_code": "", "status_filter": "Both",
    }
    params.update(overrides)
    return ProcessingJob.enqueue_advocate_search(user, params)


@pytest.mark.django_db
class TestRunAdvocateSearch:
    def _provider(self):
        """Two districts, two complexes each => 4 search calls in order:
        (Dist A, cx1), (Dist A, cx2), (Dist B, cx1), (Dist B, cx2)."""
        provider = MagicMock()
        provider.list_districts.return_value = {"1": "Dist A", "2": "Dist B"}
        provider.list_complexes.return_value = {"cx1@e@N": "Complex 1", "cx2@e@N": "Complex 2"}
        return provider

    def test_fanout_aggregates_and_dedupes_by_cnr(self, user_a):
        job = _search_job(user_a)
        provider = self._provider()
        # CNR2 appears under two complexes -> must dedupe to one.
        provider.search_by_advocate.side_effect = [
            [_ci("CNR1"), _ci("CNR2")],  # Dist A / cx1
            [_ci("CNR2")],               # Dist A / cx2 (dup)
            [_ci("CNR3")],               # Dist B / cx1
            [],                          # Dist B / cx2
        ]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)

        job.refresh_from_db()
        cnrs = sorted(r["cnr_number"] for r in job.payload["results"])
        assert cnrs == ["CNR1", "CNR2", "CNR3"]
        assert job.payload["districts_total"] == 2
        assert job.payload["complexes_searched"] == 4
        assert job.payload["failures"] == []

    def test_per_complex_failure_isolation(self, user_a):
        job = _search_job(user_a)
        provider = self._provider()
        provider.search_by_advocate.side_effect = [
            [_ci("CNR1")],                       # Dist A / cx1 ok
            CaptchaSolveError("captcha failed"),  # Dist A / cx2 fails
            [_ci("CNR2")],                       # Dist B / cx1 ok
            [_ci("CNR3")],                       # Dist B / cx2 ok
        ]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)

        job.refresh_from_db()
        assert sorted(r["cnr_number"] for r in job.payload["results"]) == ["CNR1", "CNR2", "CNR3"]
        assert len(job.payload["failures"]) == 1
        assert job.payload["failures"][0]["court_complex"] == "Complex 2"
        assert job.payload["complexes_searched"] == 3

    def test_per_district_failure_isolation(self, user_a):
        job = _search_job(user_a)
        provider = self._provider()

        def complexes(state, dist):
            if dist == "2":
                raise CourtPortalError("district 2 complex list unavailable")
            return {"cx1@e@N": "Complex 1"}

        provider.list_complexes.side_effect = complexes
        provider.search_by_advocate.return_value = [_ci("CNR1")]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)

        job.refresh_from_db()
        assert [r["cnr_number"] for r in job.payload["results"]] == ["CNR1"]
        # District B's failure is recorded with court_complex=None, Dist A still searched.
        assert len(job.payload["failures"]) == 1
        assert job.payload["failures"][0]["district"] == "Dist B"
        assert job.payload["failures"][0]["court_complex"] is None

    def test_progress_reported_per_district(self, user_a):
        job = _search_job(user_a)
        provider = self._provider()
        provider.search_by_advocate.return_value = []
        cb = MagicMock()
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job, progress_callback=cb)

        # (0,2) at start, then (1,2), (2,2) after each district.
        cb.assert_any_call(0, 2)
        cb.assert_any_call(1, 2)
        cb.assert_any_call(2, 2)

    def test_list_districts_failure_propagates(self, user_a):
        job = _search_job(user_a)
        provider = MagicMock()
        provider.list_districts.side_effect = CourtPortalError("cannot list districts")
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.time.sleep"), \
             pytest.raises(CourtPortalError):
            run_advocate_search(job)

    def test_districts_status_classifies_success_partial_failed(self, user_a):
        job = _search_job(user_a)
        provider = self._provider()  # Dist A/B, 2 complexes each
        provider.search_by_advocate.side_effect = [
            [_ci("CNR1")], [_ci("CNR2")],                    # Dist A: both complexes ok -> success
            [_ci("CNR3")], CaptchaSolveError("bad captcha"),  # Dist B: 1 ok, 1 failed -> partial
        ]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)

        job.refresh_from_db()
        status = job.payload["districts_status"]
        assert status["1"]["status"] == "success"
        assert status["1"]["complexes_ok"] == 2
        assert status["2"]["status"] == "partial"
        assert status["2"]["complexes_ok"] == 1
        assert status["2"]["complexes_failed"] == 1

    def test_districts_filter_restricts_to_requested_subset(self, user_a):
        job = _search_job(user_a, districts_filter=["2"])
        provider = self._provider()  # districts {"1": "Dist A", "2": "Dist B"}
        provider.search_by_advocate.return_value = [_ci("CNR1")]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)

        job.refresh_from_db()
        assert job.payload["districts_total"] == 1
        assert list(job.payload["districts_status"].keys()) == ["2"]
        # Only District B's 2 complexes were searched, not District A's.
        assert provider.search_by_advocate.call_count == 2

    def test_seed_results_and_seed_districts_status_are_carried_forward(self, user_a):
        job = _search_job(
            user_a,
            districts_filter=["2"],
            seed_results=[_ci("OLD1").to_dict()],
            seed_districts_status={"1": {"name": "Dist A", "status": "success", "complexes_total": 2, "complexes_ok": 2, "complexes_failed": 0}},
        )
        provider = self._provider()
        provider.search_by_advocate.return_value = [_ci("NEW1")]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)

        job.refresh_from_db()
        cnrs = sorted(r["cnr_number"] for r in job.payload["results"])
        assert cnrs == ["NEW1", "OLD1"]  # old seed result kept, new one merged in
        # Both the seeded (already-successful) district AND the newly
        # retried one appear in the final rollup.
        assert set(job.payload["districts_status"].keys()) == {"1", "2"}
        assert job.payload["districts_status"]["1"]["status"] == "success"

    def test_incremental_persistence_mid_run(self, user_a):
        """A snapshot taken BETWEEN districts (not after the whole job
        finishes) must already reflect the first district's results --
        proves _persist() writes incrementally, not only at the end."""
        job = _search_job(user_a)
        provider = self._provider()
        provider.search_by_advocate.side_effect = [
            [_ci("CNR1")], [],  # Dist A
            [_ci("CNR2")], [],  # Dist B
        ]
        snapshots = []

        def sleeping(*args, **kwargs):
            snapshots.append(ProcessingJob.objects.get(id=job.id).payload)

        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep", side_effect=sleeping):
            run_advocate_search(job)

        # By the time District B's first complex is being searched (some
        # snapshot partway through), District A must already be recorded.
        mid_run_snapshots = [s for s in snapshots if s and "1" in s.get("districts_status", {})]
        assert mid_run_snapshots, "expected at least one mid-run snapshot with District A already persisted"
        first_seen = mid_run_snapshots[0]
        assert first_seen["districts_status"]["1"]["status"] == "success"

    def test_systemic_session_failure_triggers_whole_district_retry(self, user_a):
        """Every complex in a district failing with the 'Invalid Request'
        session signature must trigger a whole-district retry (re-listing
        complexes too), not an immediate permanent failure."""
        job = _search_job(user_a)
        provider = self._provider()
        provider.list_complexes.side_effect = [
            {"cx1@e@N": "Complex 1", "cx2@e@N": "Complex 2"},  # Dist A, attempt 1
            {"cx1@e@N": "Complex 1", "cx2@e@N": "Complex 2"},  # Dist A, attempt 2 (retry re-lists)
            {"cx1@e@N": "Complex 1", "cx2@e@N": "Complex 2"},  # Dist B
        ]
        provider.search_by_advocate.side_effect = [
            CourtPortalError("...Invalid Request...Try once again"),  # Dist A cx1, attempt 1: session error
            CourtPortalError("...Invalid Request...Try once again"),  # Dist A cx2, attempt 1: session error
            [_ci("CNR1")],  # Dist A cx1, attempt 2 (after district retry): succeeds
            [_ci("CNR2")],  # Dist A cx2, attempt 2: succeeds
            [_ci("CNR3")],  # Dist B cx1
            [],             # Dist B cx2
        ]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep") as mock_sleep:
            run_advocate_search(job)

        job.refresh_from_db()
        assert job.payload["districts_status"]["1"]["status"] == "success"
        cnrs = sorted(r["cnr_number"] for r in job.payload["results"])
        assert cnrs == ["CNR1", "CNR2", "CNR3"]
        assert job.payload["failures"] == []  # the retried district recovered fully, no permanent failure recorded
        # The longer district-level cooldown must actually have been used.
        from core.services.advocate_search import DISTRICT_RETRY_BACKOFF_SECONDS
        assert any(c.args and c.args[0] == DISTRICT_RETRY_BACKOFF_SECONDS for c in mock_sleep.call_args_list)

    def test_non_systemic_mixed_failure_does_not_trigger_district_retry(self, user_a):
        """Only ONE complex failing (not all of them) with a session error
        should NOT trigger a whole-district retry -- that's the normal
        per-complex isolation path, already handled inside
        search_by_advocate's own retries."""
        job = _search_job(user_a)
        provider = self._provider()
        provider.search_by_advocate.side_effect = [
            [_ci("CNR1")],                                    # Dist A cx1 ok
            CourtPortalError("...Invalid Request..."),         # Dist A cx2: one session-classified failure
            [_ci("CNR2")], [],                                # Dist B
        ]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)

        job.refresh_from_db()
        # Only 4 search_by_advocate calls total (2 per district) -- no
        # extra district-level retry calls were made for District A.
        assert provider.search_by_advocate.call_count == 4
        assert job.payload["districts_status"]["1"]["status"] == "partial"
        assert job.payload["failures"][0]["error_type"] == "session"

    def test_unexpected_exception_in_one_complex_does_not_crash_the_run(self, user_a):
        """Regression test for a real live failure (26 Jul 2026): a very
        common advocate name made one complex's response body 25.7MB and
        the connection was cut mid-body, raising httpx.RemoteProtocolError
        -- NOT a CourtDataError, so the old code let it propagate and crash
        the entire job (results already found in earlier districts were
        only saved because of incremental persistence, but the run itself
        died and later districts were never attempted). One bad complex
        must now be isolated like any other failure."""
        import httpx

        job = _search_job(user_a)
        provider = self._provider()
        provider.search_by_advocate.side_effect = [
            [_ci("CNR1")],
            httpx.RemoteProtocolError(
                "peer closed connection without sending complete message body "
                "(received 8912896 bytes, expected 25698031)"
            ),
            [_ci("CNR2")], [],
        ]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)  # must not raise

        job.refresh_from_db()
        # The whole run completed -- District B was still attempted after
        # District A's mid-run crash, not abandoned.
        assert job.payload["districts_status"]["2"]["status"] == "success"
        assert job.payload["districts_status"]["1"]["status"] == "partial"
        cnrs = sorted(r["cnr_number"] for r in job.payload["results"])
        assert cnrs == ["CNR1", "CNR2"]
        assert len(job.payload["failures"]) == 1
        assert "RemoteProtocolError" in job.payload["failures"][0]["error"]
        assert job.payload["failures"][0]["error_type"] == "portal"

    def test_unexpected_exception_listing_complexes_does_not_crash_the_run(self, user_a):
        """Same isolation, for an unexpected (non-CourtDataError) exception
        raised while listing a district's complexes rather than searching
        one -- the district-level retry loop's broader except clause."""
        job = _search_job(user_a)
        provider = self._provider()

        def complexes(state, dist):
            if dist == "1":
                raise ValueError("totally unexpected bug")
            return {"cx1@e@N": "Complex 1", "cx2@e@N": "Complex 2"}

        provider.list_complexes.side_effect = complexes
        provider.search_by_advocate.return_value = [_ci("CNR1")]
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)  # must not raise

        job.refresh_from_db()
        assert job.payload["districts_status"]["1"]["status"] == "failed"
        assert job.payload["districts_status"]["2"]["status"] == "success"
        assert "totally unexpected bug" in job.payload["failures"][0]["error"]


class TestClassifyFailure:
    def test_invalid_request_is_session(self):
        from core.services.advocate_search import _classify_failure
        assert _classify_failure("...Invalid Request...Try once again") == "session"

    def test_invalid_captcha_is_captcha(self):
        from core.services.advocate_search import _classify_failure
        assert _classify_failure("Invalid Captcha... ") == "captcha"

    def test_empty_response_is_data(self):
        from core.services.advocate_search import _classify_failure
        assert _classify_failure("District Courts advocate search returned an empty response -- dist_code/court_complex_code must both be a real, valid district and court complex") == "data"

    def test_unrecognized_text_is_portal(self):
        from core.services.advocate_search import _classify_failure
        assert _classify_failure("connection timed out") == "portal"


# ---------------------------------------------------------------------------
# run_advocate_import (unchanged behavior, still async per-case)
# ---------------------------------------------------------------------------


def _fake_case_data(cnr: str) -> CourtCaseData:
    return CourtCaseData(
        cnr=cnr,
        petitioner="Suresh Kumar",
        respondent="State Bank",
        court_name="Civil Court, Pune",
        party_advocate_data={"petitioner_advocates": ["A. Sharma"], "respondent_advocates": []},
    )


IMPORT_CNR = "MHAU019999992024"


def _import_one(user, item, data, **job_kwargs) -> Case:
    """Import a single search result with the portal fetch mocked to return
    `data`, and hand back the Case it created."""
    job = ProcessingJob.enqueue_advocate_import(user, [item], **job_kwargs)
    with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
         patch("core.services.advocate_import.time.sleep"):
        mock_get_provider.return_value.fetch_case.return_value = data
        run_advocate_import(job)

    job.refresh_from_db()
    return Case.objects.get(id=job.payload["created"][0])


@pytest.mark.django_db
class TestAdvocateImport:
    def test_creates_cases_owned_by_job_owner(self, user_a):
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [{"cnr_number": "MHAU019999992024", "case_number": "123/2024", "petitioner": "Suresh Kumar", "respondent": "State Bank"}],
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.return_value = _fake_case_data("MHAU019999992024")
            run_advocate_import(job)

        job.refresh_from_db()
        assert job.payload["created"]
        case = Case.objects.get(id=job.payload["created"][0])
        assert case.owner_id == user_a.id
        assert case.tracking_enabled is True
        assert case.party_advocate_data["petitioner_advocates"] == ["A. Sharma"]

    def test_title_is_petitioner_vs_respondent_and_case_number_is_kept(self, user_a):
        # Same format as the CNR quick-add flow ("Ramesh Kumar vs TSSPDCL").
        # Used to be the bare case number, which also left the case with no
        # human-readable name at all in the case list.
        case = _import_one(
            user_a,
            {
                "cnr_number": IMPORT_CNR,
                "case_number": "123/2024",
                "petitioner": "Suresh Kumar",
                "respondent": "State Bank",
            },
            _fake_case_data(IMPORT_CNR),
        )
        assert case.title == "Suresh Kumar vs State Bank"
        assert case.case_number == "123/2024"

    def test_court_record_names_win_over_search_result_names(self, user_a):
        case = _import_one(
            user_a,
            {"cnr_number": IMPORT_CNR, "case_number": "123/2024", "petitioner": "S. Kumar", "respondent": "SBI"},
            _fake_case_data(IMPORT_CNR),
        )
        assert case.title == "Suresh Kumar vs State Bank"

    def test_title_comes_from_the_court_record_when_the_search_result_has_no_parties(self, user_a):
        case = _import_one(
            user_a, {"cnr_number": IMPORT_CNR, "case_number": "123/2024"}, _fake_case_data(IMPORT_CNR)
        )
        assert case.title == "Suresh Kumar vs State Bank"

    def test_title_falls_back_to_case_number_only_when_no_party_is_known(self, user_a):
        no_parties = dataclasses.replace(_fake_case_data(IMPORT_CNR), petitioner="", respondent="")
        case = _import_one(user_a, {"cnr_number": IMPORT_CNR, "case_number": "123/2024"}, no_parties)
        assert case.title == "123/2024"

    def test_one_sided_parties_give_just_that_name(self, user_a):
        one_sided = dataclasses.replace(_fake_case_data(IMPORT_CNR), petitioner="", respondent="")
        case = _import_one(
            user_a,
            {"cnr_number": IMPORT_CNR, "case_number": "123/2024", "petitioner": "Suresh Kumar"},
            one_sided,
        )
        assert case.title == "Suresh Kumar"

    def test_opposing_party_is_the_respondent_for_a_petitioner_side_advocate(self, user_a):
        case = _import_one(
            user_a,
            {"cnr_number": IMPORT_CNR, "case_number": "123/2024"},
            _fake_case_data(IMPORT_CNR),
            advocate_name="A. Sharma",
        )
        assert case.user_party_role == "petitioner"
        assert case.opposing_party == "State Bank"

    def test_opposing_party_is_the_petitioner_for_a_respondent_side_advocate(self, user_a):
        respondent_side = dataclasses.replace(
            _fake_case_data(IMPORT_CNR),
            party_advocate_data={"petitioner_advocates": [], "respondent_advocates": ["A. Sharma"]},
        )
        case = _import_one(
            user_a,
            {"cnr_number": IMPORT_CNR, "case_number": "123/2024"},
            respondent_side,
            advocate_name="A. Sharma",
        )
        assert case.user_party_role == "respondent"
        assert case.opposing_party == "Suresh Kumar"

    @pytest.mark.parametrize(
        "job_kwargs",
        [{"advocate_name": "Someone Else"}, {"bar_code": "MAH/1234/2015"}, {}],
        ids=["name-mismatch", "bar-code-search", "no-identity"],
    )
    def test_opposing_party_stays_blank_when_the_role_is_unknown(self, user_a, job_kwargs):
        # Which of the two is the advocate's opponent can't be told without
        # the role -- a guess would put the wrong party on the record.
        case = _import_one(
            user_a,
            {"cnr_number": IMPORT_CNR, "case_number": "123/2024"},
            _fake_case_data(IMPORT_CNR),
            **job_kwargs,
        )
        assert case.user_party_role == "unknown"
        assert case.opposing_party is None
        # The title needs no role.
        assert case.title == "Suresh Kumar vs State Bank"

    def test_failed_fetch_still_leaves_the_case_titled_from_the_search_result(self, user_a):
        # The row is created before the fetch and kept when the fetch fails,
        # so it must not be left titled with its bare case number.
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [
                {
                    "cnr_number": IMPORT_CNR,
                    "case_number": "123/2024",
                    "petitioner": "Suresh Kumar",
                    "respondent": "State Bank",
                }
            ],
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.side_effect = CaptchaSolveError("failed")
            run_advocate_import(job)

        job.refresh_from_db()
        assert job.payload["created"] == []
        assert len(job.payload["failed"]) == 1
        assert Case.objects.get(owner=user_a, case_number="123/2024").title == "Suresh Kumar vs State Bank"

    def test_overlong_party_names_are_clipped_and_do_not_abort_the_batch(self, user_a):
        # title is 500 chars and opposing_party 255; a many-party case can
        # exceed both. An unclipped value is a DataError, which would take
        # every later item in the batch down with it.
        long_data = dataclasses.replace(
            _fake_case_data("CNR0000000000001"), petitioner="P" * 400, respondent="R" * 400
        )
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [
                {
                    "cnr_number": "CNR0000000000001",
                    "case_number": "1/2024",
                    "petitioner": "P" * 400,
                    "respondent": "R" * 400,
                },
                {"cnr_number": "CNR0000000000002", "case_number": "2/2024"},
            ],
            advocate_name="A. Sharma",
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.side_effect = [
                long_data,
                _fake_case_data("CNR0000000000002"),
            ]
            run_advocate_import(job)

        job.refresh_from_db()
        assert job.payload["failed"] == []
        assert len(job.payload["created"]) == 2
        long_case = Case.objects.get(id=job.payload["created"][0])
        assert len(long_case.title) == 500
        assert long_case.title.startswith("P" * 400)
        assert len(long_case.opposing_party) == 255

    def test_auto_detects_party_role_on_clean_match(self, user_a):
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}],
            advocate_name="A. Sharma",
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.return_value = _fake_case_data("MHAU019999992024")
            run_advocate_import(job)

        job.refresh_from_db()
        case = Case.objects.get(id=job.payload["created"][0])
        assert case.user_party_role == "petitioner"

    def test_party_role_stays_unknown_on_no_match(self, user_a):
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}],
            advocate_name="Someone Else",
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.return_value = _fake_case_data("MHAU019999992024")
            run_advocate_import(job)

        job.refresh_from_db()
        case = Case.objects.get(id=job.payload["created"][0])
        assert case.user_party_role == "unknown"

    def test_party_role_stays_unknown_for_bar_code_search(self, user_a):
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}],
            bar_code="MAH/1234/2015",
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.return_value = _fake_case_data("MHAU019999992024")
            run_advocate_import(job)

        job.refresh_from_db()
        case = Case.objects.get(id=job.payload["created"][0])
        assert case.user_party_role == "unknown"

    def test_duplicate_cnr_for_same_user_is_skipped(self, user_a):
        Case.objects.create(
            owner=user_a, case_number="EXISTING-1", title="Existing", client_name="",
            cnr_number="MHAU019999992024",
        )
        job = ProcessingJob.enqueue_advocate_import(
            user_a, [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}]
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            run_advocate_import(job)

        job.refresh_from_db()
        assert job.payload["skipped_duplicate"] == ["MHAU019999992024"]
        assert job.payload["created"] == []
        assert mock_get_provider.return_value.fetch_case.call_count == 0

    def test_case_number_shared_with_another_owner_is_imported_independently(self, user_a, user_b):
        """case_number is unique per owner, not globally -- Bob already
        tracking "123/2024" must not stop Alice from importing her own
        independent row for the same case_number (co-counsel, opposing
        counsel, or simply a coincidence)."""
        bobs_case = Case.objects.create(
            owner=user_b, case_number="123/2024", title="Bob's case", client_name="",
        )
        job = ProcessingJob.enqueue_advocate_import(
            user_a, [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}]
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.return_value = _fake_case_data("MHAU019999992024")
            run_advocate_import(job)

        job.refresh_from_db()
        assert job.payload["skipped_conflict"] == []
        assert len(job.payload["created"]) == 1
        alices_case = Case.objects.get(id=job.payload["created"][0])
        assert alices_case.case_number == "123/2024"
        assert alices_case.owner_id == user_a.id
        assert alices_case.id != bobs_case.id

    def test_case_number_collision_with_own_existing_case_is_skipped_not_500(self, user_a):
        """A DIFFERENT CNR whose case_number happens to match one this
        SAME advocate already has is still a genuine collision -- the
        residual, same-owner-only purpose of the (owner, case_number)
        UniqueConstraint."""
        Case.objects.create(
            owner=user_a, case_number="123/2024", title="Alice's existing case", client_name="",
        )
        job = ProcessingJob.enqueue_advocate_import(
            user_a, [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}]
        )
        with patch("core.services.court_tracking.get_provider"), \
             patch("core.services.advocate_import.time.sleep"):
            run_advocate_import(job)

        job.refresh_from_db()
        assert job.payload["skipped_conflict"] == ["MHAU019999992024"]
        assert job.payload["created"] == []

    def test_one_captcha_failure_does_not_abort_the_batch(self, user_a):
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [
                {"cnr_number": "CNR0000000000001", "case_number": "1/2024"},
                {"cnr_number": "CNR0000000000002", "case_number": "2/2024"},
            ],
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep"):
            mock_get_provider.return_value.fetch_case.side_effect = [
                CaptchaSolveError("failed"),
                _fake_case_data("CNR0000000000002"),
            ]
            run_advocate_import(job)

        job.refresh_from_db()
        assert len(job.payload["failed"]) == 1
        assert job.payload["failed"][0]["cnr"] == "CNR0000000000001"
        assert len(job.payload["created"]) == 1

    def test_sleeps_between_cases(self, user_a):
        job = ProcessingJob.enqueue_advocate_import(
            user_a,
            [
                {"cnr_number": "CNR0000000000001", "case_number": "1/2024"},
                {"cnr_number": "CNR0000000000002", "case_number": "2/2024"},
                {"cnr_number": "CNR0000000000003", "case_number": "3/2024"},
            ],
        )
        with patch("core.services.court_tracking.get_provider") as mock_get_provider, \
             patch("core.services.advocate_import.time.sleep") as mock_sleep:
            mock_get_provider.return_value.fetch_case.side_effect = lambda cfg: _fake_case_data(cfg["cnr"])
            run_advocate_import(job)

        assert mock_sleep.call_count == 2  # N-1 delays for 3 items


class TestCaseLabelHelpers:
    """The rules the import and the CNR quick-add flow share."""

    @pytest.mark.parametrize(
        "petitioner, respondent, expected",
        [
            ("Ramesh Kumar", "TSSPDCL", "Ramesh Kumar vs TSSPDCL"),
            ("Ramesh Kumar", "", "Ramesh Kumar"),
            ("", "TSSPDCL", "TSSPDCL"),
            ("", "", "WP/1/2026"),
        ],
    )
    def test_build_case_title(self, petitioner, respondent, expected):
        assert build_case_title(petitioner, respondent, "WP/1/2026") == expected

    @pytest.mark.parametrize(
        "role, expected",
        [("petitioner", "R"), ("respondent", "P"), ("unknown", None)],
    )
    def test_opposing_party_for_role(self, role, expected):
        assert opposing_party_for_role(role, "P", "R") == expected

    def test_opposing_party_is_none_when_that_side_has_no_name(self):
        assert opposing_party_for_role("petitioner", "P", "") is None


# ---------------------------------------------------------------------------
# backfill_import_case_titles (repairs cases imported before the fix)
# ---------------------------------------------------------------------------


def _imported_case(owner, number, cnr, **extra) -> Case:
    """A case as the old import left it: titled with its own number, no
    opposing party, tracking on."""
    extra.setdefault("title", number)
    return Case.objects.create(
        owner=owner, case_number=number, client_name="", cnr_number=cnr, tracking_enabled=True, **extra
    )


def _named(owner, number, cnr, **extra) -> Case:
    extra.setdefault("petitioner_name", "Suresh Kumar")
    extra.setdefault("respondent_name", "State Bank")
    return _imported_case(owner, number, cnr, **extra)


def _backfill(*args) -> str:
    out = StringIO()
    call_command("backfill_import_case_titles", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestBackfillImportCaseTitles:
    def test_sets_title_and_opposing_party_and_keeps_the_case_number(self, user_a):
        case = _named(user_a, "123/2024", "CNR0000000000001", user_party_role="petitioner")

        _backfill("--owner", "alice")

        case.refresh_from_db()
        assert case.title == "Suresh Kumar vs State Bank"
        assert case.opposing_party == "State Bank"
        assert case.case_number == "123/2024"

    def test_respondent_side_gets_the_petitioner_as_opposing_party(self, user_a):
        case = _named(user_a, "123/2024", "CNR0000000000001", user_party_role="respondent")

        _backfill("--owner", "alice")

        case.refresh_from_db()
        assert case.opposing_party == "Suresh Kumar"

    def test_dry_run_reports_but_writes_nothing(self, user_a):
        case = _named(user_a, "123/2024", "CNR0000000000001", user_party_role="petitioner")

        out = _backfill("--owner", "alice", "--dry-run")

        case.refresh_from_db()
        assert case.title == "123/2024"
        assert case.opposing_party is None
        assert "would update 1" in out
        assert "Suresh Kumar vs State Bank" in out

    def test_a_customised_title_and_an_existing_opposing_party_are_left_alone(self, user_a):
        case = _named(
            user_a,
            "123/2024",
            "CNR0000000000001",
            title="Sharma family land matter",
            opposing_party="Typed by the advocate",
            user_party_role="petitioner",
        )

        out = _backfill("--owner", "alice")

        case.refresh_from_db()
        assert case.title == "Sharma family land matter"
        assert case.opposing_party == "Typed by the advocate"
        assert "Updated 0" in out

    def test_a_customised_title_does_not_stop_the_opposing_party_being_filled(self, user_a):
        case = _named(
            user_a, "123/2024", "CNR0000000000001", title="Sharma matter", user_party_role="petitioner"
        )

        _backfill("--owner", "alice")

        case.refresh_from_db()
        assert case.title == "Sharma matter"
        assert case.opposing_party == "State Bank"

    def test_unknown_role_gets_a_title_but_no_opposing_party_and_is_reported(self, user_a):
        case = _named(user_a, "123/2024", "CNR0000000000001")

        out = _backfill("--owner", "alice")

        case.refresh_from_db()
        assert case.title == "Suresh Kumar vs State Bank"
        assert not case.opposing_party
        assert "isn't set" in out
        assert str(case.id) in out

    def test_case_with_no_party_names_is_skipped_and_reported(self, user_a):
        case = _imported_case(user_a, "123/2024", "CNR0000000000001")

        out = _backfill("--owner", "alice")

        case.refresh_from_db()
        assert case.title == "123/2024"
        assert "backfill_party_names" in out
        assert str(case.id) in out

    def test_only_the_owners_cases_inside_the_id_range_are_touched(self, user_a, user_b):
        below = _named(user_a, "1/2024", "CNR0000000000001")
        inside = _named(user_a, "2/2024", "CNR0000000000002")
        # Another advocate's case whose id falls inside the range.
        theirs = _named(user_b, "3/2024", "CNR0000000000003")
        above = _named(user_a, "4/2024", "CNR0000000000004")

        _backfill("--owner", "alice", "--min-id", str(inside.id), "--max-id", str(above.id - 1))

        for case, expected in [
            (below, "1/2024"),
            (inside, "Suresh Kumar vs State Bank"),
            (theirs, "3/2024"),
            (above, "4/2024"),
        ]:
            case.refresh_from_db()
            assert case.title == expected

    def test_cases_without_a_cnr_are_left_alone(self, user_a):
        manual = Case.objects.create(
            owner=user_a,
            case_number="MANUAL-1",
            title="MANUAL-1",
            client_name="",
            petitioner_name="Suresh Kumar",
            respondent_name="State Bank",
        )

        _backfill("--owner", "alice")

        manual.refresh_from_db()
        assert manual.title == "MANUAL-1"

    def test_second_run_changes_nothing(self, user_a):
        case = _named(user_a, "123/2024", "CNR0000000000001", user_party_role="petitioner")
        _backfill("--owner", "alice")
        case.refresh_from_db()
        before = (case.title, case.opposing_party)

        out = _backfill("--owner", "alice")

        case.refresh_from_db()
        assert (case.title, case.opposing_party) == before
        assert "Updated 0" in out

    def test_unknown_owner_is_a_command_error(self, user_a):
        with pytest.raises(CommandError):
            _backfill("--owner", "nobody")


# ---------------------------------------------------------------------------
# Import endpoints
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdvocateImportEndpoints:
    def test_start_import_enqueues_job(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/import/",
            {
                "court_type": "district",
                "selected": [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}],
            },
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.job_type == "advocate_import"
        assert job.payload["selected"][0]["court_type"] == "district"

    def test_search_job_id_threads_advocate_name_into_import_payload(self, client_a, user_a):
        search_job = ProcessingJob.objects.create(
            owner=user_a,
            job_type="advocate_search",
            payload={"advocate_name": "A. Sharma", "bar_code": ""},
        )
        resp = client_a.post(
            "/api/cases/search-advocate/import/",
            {
                "court_type": "district",
                "selected": [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}],
                "search_job_id": search_job.id,
            },
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.payload["advocate_name"] == "A. Sharma"
        assert job.payload["bar_code"] == ""

    def test_other_users_search_job_id_is_ignored_not_leaked(self, client_a, user_b):
        # search_job_id pointing at another user's job must not leak that
        # job's advocate_name/bar_code -- silently falls back to "" (no
        # auto-detection attempted), not an error.
        other_search_job = ProcessingJob.objects.create(
            owner=user_b, job_type="advocate_search", payload={"advocate_name": "Bob's Search"}
        )
        resp = client_a.post(
            "/api/cases/search-advocate/import/",
            {
                "court_type": "district",
                "selected": [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}],
                "search_job_id": other_search_job.id,
            },
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.payload["advocate_name"] == ""

    def test_missing_search_job_id_defaults_to_no_auto_detection(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/import/",
            {
                "court_type": "district",
                "selected": [{"cnr_number": "MHAU019999992024", "case_number": "123/2024"}],
            },
            format="json",
        )
        assert resp.status_code == 202
        job = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert job.payload["advocate_name"] == ""
        assert job.payload["bar_code"] == ""

    def test_empty_selection_rejected(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/import/",
            {"court_type": "district", "selected": []},
            format="json",
        )
        assert resp.status_code == 400

    def test_batch_size_capped(self, client_a):
        selected = [{"cnr_number": f"CNR{i:013d}"} for i in range(101)]
        resp = client_a.post(
            "/api/cases/search-advocate/import/",
            {"court_type": "district", "selected": selected},
            format="json",
        )
        assert resp.status_code == 400

    def test_status_reports_outcome(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a,
            job_type="advocate_import",
            status="succeeded",
            payload={"created": [1, 2], "skipped_duplicate": [], "skipped_conflict": [], "failed": []},
        )
        resp = client_a.get(f"/api/cases/search-advocate/import/{job.id}/")
        assert resp.status_code == 200
        assert resp.data["status"] == "succeeded"
        assert resp.data["created"] == [1, 2]

    def test_other_users_import_job_is_not_visible(self, client_a, user_b):
        job = ProcessingJob.objects.create(owner=user_b, job_type="advocate_import", payload={})
        resp = client_a.get(f"/api/cases/search-advocate/import/{job.id}/")
        assert resp.status_code == 404


@pytest.mark.django_db
class TestAdvocateSearchPreferenceIsolation:
    def test_preference_scoped_to_owner(self, client_a, client_b, user_a):
        AdvocateSearchPreference.objects.create(
            owner=user_a, court_type="district", hierarchy_config={"state_code": "1"}
        )
        resp = client_b.get("/api/cases/search-advocate/preference/")
        assert resp.status_code == 200
        assert resp.data is None

        resp = client_a.get("/api/cases/search-advocate/preference/")
        assert resp.status_code == 200
        assert resp.data["hierarchy_config"] == {"state_code": "1"}


# ---------------------------------------------------------------------------
# _district_search_by_advocate's hand-rolled retry loop (25 Jul 2026 fix):
# regression coverage for the two bugs found live --
#   1. "Invalid Captcha" from submitAdvName raises ServerError (errormsg is
#      populated), not CaptchaError -- bharat-courts' own
#      _post_with_captcha_retry only catches CaptchaError, so it silently
#      delivered just 1 real attempt instead of up to 5. This method no
#      longer goes through that vendored retry helper at all.
#   2. A blank/wrong-length OCR decode was being submitted to the server
#      (a guaranteed-fail guess) instead of silently refetching.
# Also covers: empty adv_data (missing/invalid dist_code or
# court_complex_code) must raise CourtPortalError, not silently return [].
# ---------------------------------------------------------------------------


def _mock_district_client(*, captchas, post_ajax_results):
    """A MagicMock standing in for _TokenSeedingDistrictClient, used as an
    async context manager. captchas/post_ajax_results are consumed in
    order, one per retry-loop attempt (post_ajax_results only consumed on
    attempts where captchas didn't yield a blank string)."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client._init_session = AsyncMock()
    client._setup_court = AsyncMock()
    client._solve_captcha = AsyncMock(side_effect=captchas)
    client._post_ajax = AsyncMock(side_effect=post_ajax_results)
    return client


HIERARCHY = {"state_code": "1", "dist_code": "26", "court_complex_code": "1010307", "est_code": "2"}


class TestDistrictSearchByAdvocateRetryLogic:
    def test_blank_ocr_decode_skips_submit_without_network_call(self):
        """A blank _solve_captcha() result must NOT reach _post_ajax at
        all (fix #2) -- it should silently loop to a fresh captcha fetch."""
        from core.services.court_data.ecourts_provider import EcourtsProvider

        client = _mock_district_client(
            captchas=["", "abc123"],  # blank first, valid second
            post_ajax_results=[{"adv_data": "<table></table>"}],  # only ONE real post
        )
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
             patch("core.services.court_data.ecourts_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = EcourtsProvider()
            asyncio.run(
                provider._district_search_by_advocate(
                    HIERARCHY, advocate_name="Patil", bar_state="", bar_code="", bar_year="", status_filter="Both",
                )
            )
        assert client._solve_captcha.call_count == 2
        assert client._post_ajax.call_count == 1  # the blank decode never posted

    def test_server_error_invalid_captcha_is_retried_not_fatal(self):
        """Confirms fix #1: a ServerError (the real shape "Invalid Captcha"
        responses take) is caught and retried here, not left to a vendored
        helper that only catches CaptchaError."""
        from core.services.court_data.ecourts_provider import EcourtsProvider

        client = _mock_district_client(
            captchas=["wrong1", "right1"],
            post_ajax_results=[DistrictServerError("Invalid Captcha... "), {"adv_data": "<table></table>"}],
        )
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
             patch("core.services.court_data.ecourts_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = EcourtsProvider()
            result = asyncio.run(
                provider._district_search_by_advocate(
                    HIERARCHY, advocate_name="Patil", bar_state="", bar_code="", bar_year="", status_filter="Both",
                )
            )
        assert result == []  # empty parse of "<table></table>" -- just proving it didn't raise
        assert client._post_ajax.call_count == 2

    def test_empty_adv_data_raises_court_portal_error_not_silent_zero(self):
        """Verified live 25 Jul 2026: submitting without a real dist_code
        AND court_complex_code returns HTTP 200 with a blank body. That
        must surface as an error, not an indistinguishable empty result."""
        from core.services.court_data.ecourts_provider import ADVOCATE_SEARCH_MAX_ATTEMPTS, EcourtsProvider

        client = _mock_district_client(
            captchas=["abc123"] * ADVOCATE_SEARCH_MAX_ATTEMPTS,
            post_ajax_results=[{"adv_data": ""}] * ADVOCATE_SEARCH_MAX_ATTEMPTS,
        )
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
             patch("core.services.court_data.ecourts_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = EcourtsProvider()
            with pytest.raises(CourtPortalError, match="empty response"):
                asyncio.run(
                    provider._district_search_by_advocate(
                        {**HIERARCHY, "dist_code": "0", "court_complex_code": "0"},
                        advocate_name="Patil", bar_state="", bar_code="", bar_year="", status_filter="Both",
                    )
                )
        assert client._post_ajax.call_count == ADVOCATE_SEARCH_MAX_ATTEMPTS

    def test_exhausting_all_attempts_on_captcha_raises_captcha_solve_error(self):
        from core.services.court_data.ecourts_provider import ADVOCATE_SEARCH_MAX_ATTEMPTS, EcourtsProvider

        client = _mock_district_client(
            captchas=[""] * ADVOCATE_SEARCH_MAX_ATTEMPTS,  # OCR never produces a valid guess
            post_ajax_results=[],
        )
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
             patch("core.services.court_data.ecourts_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = EcourtsProvider()
            with pytest.raises(CaptchaSolveError):
                asyncio.run(
                    provider._district_search_by_advocate(
                        HIERARCHY, advocate_name="Patil", bar_state="", bar_code="", bar_year="", status_filter="Both",
                    )
                )
        client._post_ajax.assert_not_called()  # never wasted a submit on a blank decode


# ---------------------------------------------------------------------------
# Token seeding fix (the list_districts "Invalid Request" root cause)
# ---------------------------------------------------------------------------


class TestTokenSeeding:
    """_TokenSeedingDistrictClient must (a) establish the session cookie via
    the bare home page, (b) pin BOTH live anti-scraping headers from
    components.js -- the second header's KEY rotates same as its value, it
    is never the static "abc" the 24 Jul fix assumed -- and (c) seed a real
    app_token from casestatus/index. Re-root-caused live 14 Aug 2026 after
    the 24 Jul fix (app_token + delimeter alone) turned out incomplete: the
    session cookie was never being established at all, and "abc" was a
    header key the server was never actually checking, silently equivalent
    to not sending the second header. See the block comment above
    _TokenSeedingDistrictClient for the full live-diff account."""

    def _client(self, *, delimeter_js="", casestatus_html=""):
        client = _TokenSeedingDistrictClient()
        # _init_session GETs the home page first (session cookie), then
        # components.js, then casestatus/index.
        def fake_get(url, **kw):
            r = MagicMock()
            r.text = delimeter_js if "components.js" in url else casestatus_html
            return r
        client._http = MagicMock()
        client._http.get = AsyncMock(side_effect=fake_get)
        fake_httpx = MagicMock()
        fake_httpx.headers = {}
        client._http._ensure_client = MagicMock(return_value=fake_httpx)
        client._fake_httpx = fake_httpx
        return client

    def test_seeds_token_from_casestatus_page(self):
        client = self._client(
            casestatus_html="<input name=\"app_token\" id='app_token' value=\"abc123def456\">"
        )
        asyncio.run(client._init_session())
        assert client._app_token == "abc123def456"

    def test_establishes_session_cookie_via_home_page_before_anything_else(self):
        """Confirmed live 14 Aug 2026: SERVICES_SESSID/JSESSION are set ONLY
        by the bare home page GET -- neither components.js nor
        casestatus/index sets them. A fresh client's cookie jar is empty, so
        skipping this means every later request in the session goes out
        session-less."""
        client = self._client(casestatus_html="id='app_token' value=\"deadbeef00\"")
        asyncio.run(client._init_session())
        first_url = client._http.get.call_args_list[0].args[0]
        assert first_url.rstrip("/").endswith("ecourtindia_v6")
        assert "components.js" not in first_url
        assert "casestatus" not in first_url

    def test_pins_live_delimeter_under_its_own_rotating_second_key(self):
        """The second header's KEY is scraped live from the same
        headers:{...} literal the delimeter value comes from -- e.g.
        `"delimeter": delimeter, "Uweuyfhsj347": delimeter` -- never a
        hardcoded "abc". Live 14 Aug 2026 the key was "Uweuyfhsj347", then
        "Dyiguyqeghdf", then "Byiewufgj753" across three fetches minutes
        apart -- as rotating as the value itself."""
        client = self._client(
            delimeter_js=(
                'function ajaxCall(o){var delimeter="vmgasjnn98dsf846";'
                '$.ajax({headers: {"delimeter": delimeter, "Uweuyfhsj347":delimeter}});}'
            ),
            casestatus_html="id='app_token' value=\"deadbeef00\"",
        )
        asyncio.run(client._init_session())
        assert client._fake_httpx.headers["delimeter"] == "vmgasjnn98dsf846"
        assert client._fake_httpx.headers["Uweuyfhsj347"] == "vmgasjnn98dsf846"
        assert "abc" not in client._fake_httpx.headers

    def test_no_headers_pinned_when_second_header_pattern_not_found(self):
        """A half-correct pin (delimeter alone, no second header, or a
        second header under the wrong key) is silently equivalent to
        sending neither -- confirmed live the portal rejects unless both
        arrive together. Better to pin nothing and log a warning than pin
        a value that looks right but the server was never checking."""
        client = self._client(
            delimeter_js='function ajaxCall(o){var delimeter="vmgasjnn98dsf846";}',  # no headers:{...} block
            casestatus_html="id='app_token' value=\"deadbeef00\"",
        )
        asyncio.run(client._init_session())
        assert client._fake_httpx.headers == {}

    def test_seeds_from_casestatus_index_url(self):
        client = self._client(casestatus_html="id='app_token' value=\"deadbeef00\"")
        asyncio.run(client._init_session())
        # The LAST get is the casestatus page (home page + components.js
        # are fetched first).
        assert "casestatus/index" in client._http.get.call_args.args[0]

    def test_falls_back_to_vendored_when_no_token(self):
        client = self._client(casestatus_html="<html>no token here</html>")
        with patch.object(
            _TokenSeedingDistrictClient.__mro__[1], "_init_session", new_callable=AsyncMock
        ) as base_init:
            asyncio.run(client._init_session())
            base_init.assert_awaited_once()


# ---------------------------------------------------------------------------
# System-wide single-in-flight cap on advocate_search / advocate_import
# ---------------------------------------------------------------------------


_SEARCH_BODY = {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "1"}
_IMPORT_BODY = {"court_type": "district", "selected": [{"cnr_number": "X1", "case_number": "1/2024"}]}


@pytest.mark.django_db
class TestConcurrencyCap:
    def test_enqueue_helper_raises_when_active(self, user_a):
        ProcessingJob.enqueue_advocate_search(user_a, {"state_code": "1"})
        with pytest.raises(JobAlreadyRunningError):
            ProcessingJob.enqueue_advocate_search(user_a, {"state_code": "1"})

    def test_second_search_rejected_409(self, client_a):
        assert client_a.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json").status_code == 202
        resp = client_a.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json")
        assert resp.status_code == 409
        assert resp.data["code"] == "search_already_running"

    def test_search_cap_is_system_wide_across_users(self, client_a, client_b):
        assert client_a.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json").status_code == 202
        # A different user is still blocked -- the cap is global, not per-owner.
        resp = client_b.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json")
        assert resp.status_code == 409

    def test_second_import_rejected_409(self, client_a):
        assert client_a.post("/api/cases/search-advocate/import/", _IMPORT_BODY, format="json").status_code == 202
        resp = client_a.post("/api/cases/search-advocate/import/", _IMPORT_BODY, format="json")
        assert resp.status_code == 409
        assert resp.data["code"] == "import_already_running"

    def test_search_and_import_are_independent(self, client_a):
        assert client_a.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json").status_code == 202
        # An active search must NOT block an import (different job type).
        assert client_a.post("/api/cases/search-advocate/import/", _IMPORT_BODY, format="json").status_code == 202

    def test_new_search_allowed_after_previous_finished(self, client_a):
        r1 = client_a.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json")
        assert r1.status_code == 202
        ProcessingJob.objects.filter(id=r1.data["job_id"]).update(status="succeeded")
        assert client_a.post("/api/cases/search-advocate/", _SEARCH_BODY, format="json").status_code == 202
