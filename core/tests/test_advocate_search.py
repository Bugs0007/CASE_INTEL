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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bharat_courts import CaseInfo
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import AdvocateSearchPreference, Case, JobAlreadyRunningError, ProcessingJob
from core.services.advocate_import import run_advocate_import
from core.services.advocate_search import run_advocate_search
from core.services.court_data import CaptchaSolveError, CourtPortalError
from core.services.court_data.ecourts_provider import _TokenSeedingDistrictClient, split_bar_code
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
            },
        )
        resp = client_a.get(f"/api/cases/search-advocate/{job.id}/")
        assert resp.status_code == 200
        assert resp.data["status"] == "succeeded"
        assert len(resp.data["results"]) == 2
        assert len(resp.data["failures"]) == 1
        assert resp.data["districts_total"] == 30

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

    def test_case_number_conflict_with_another_owner_is_skipped_not_500(self, user_a, user_b):
        Case.objects.create(
            owner=user_b, case_number="123/2024", title="Bob's case", client_name="",
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
# Token seeding fix (the list_districts "Invalid Request" root cause)
# ---------------------------------------------------------------------------


class TestTokenSeeding:
    """_TokenSeedingDistrictClient must seed a real app_token from the
    casestatus/index page -- the vendored client GETs the tokenless "/"
    home page and sent app_token="" (the "Invalid Request" root cause)."""

    def _client_with_page(self, html: str):
        client = _TokenSeedingDistrictClient()
        resp = MagicMock()
        resp.text = html
        client._http = MagicMock()
        client._http.get = AsyncMock(return_value=resp)
        return client

    def test_seeds_token_from_page(self):
        client = self._client_with_page(
            "<input type=\"hidden\" name=\"app_token\" id='app_token' value=\"abc123def456\">"
        )
        asyncio.run(client._init_session())
        assert client._app_token == "abc123def456"

    def test_seeds_from_casestatus_index_url(self):
        client = self._client_with_page("id='app_token' value=\"deadbeef00\"")
        asyncio.run(client._init_session())
        called_url = client._http.get.call_args.args[0]
        assert "casestatus/index" in called_url

    def test_falls_back_to_vendored_when_no_token(self):
        client = self._client_with_page("<html>no token here</html>")
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
