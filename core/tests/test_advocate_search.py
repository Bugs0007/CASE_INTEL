"""
Advocate search + bulk import tests.

Mocks at the same boundary the rest of the codebase already treats as
authoritative: core.services.court_data.get_provider() (see base.py's
"CourtDataProvider is the ONLY interface the rest of Case Intel talks to"
docstring) for the view/import-service tests, plus a couple of pure unit
tests for split_bar_code (no mocking needed). No live eCourts calls.
"""

from unittest.mock import patch

import pytest
from bharat_courts import CaseInfo
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import AdvocateSearchPreference, Case, ProcessingJob
from core.services.advocate_import import run_advocate_import
from core.services.court_data import CaptchaSolveError, CaseNotFoundError, CourtPortalError
from core.services.court_data.ecourts_provider import split_bar_code
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


VALID_HIERARCHY = {"state_code": "1", "dist_code": "2", "court_complex_code": "3"}


def _case_info(**overrides) -> CaseInfo:
    defaults = dict(
        case_number="123/2024",
        case_type="Civil Suit",
        cnr_number="MHAU019999992024",
        petitioner="Suresh Kumar",
        respondent="State Bank",
        status="Pending",
        court_name="Civil Court, Pune",
    )
    defaults.update(overrides)
    return CaseInfo(**defaults)


# ---------------------------------------------------------------------------
# AdvocateSearchView
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdvocateSearchView:
    def test_zero_results(self, client_a):
        with patch("core.views.advocate_search.get_provider") as mock_get_provider:
            mock_get_provider.return_value.search_by_advocate.return_value = []
            resp = client_a.post(
                "/api/cases/search-advocate/",
                {
                    "name_or_bar_code": "Suresh",
                    "court_type": "district",
                    "hierarchy_config": VALID_HIERARCHY,
                },
                format="json",
            )
        assert resp.status_code == 200
        assert resp.data["results"] == []

    def test_valid_name_search_returns_results(self, client_a):
        with patch("core.views.advocate_search.get_provider") as mock_get_provider:
            mock_get_provider.return_value.search_by_advocate.return_value = [_case_info()]
            resp = client_a.post(
                "/api/cases/search-advocate/",
                {
                    "name_or_bar_code": "Suresh",
                    "court_type": "district",
                    "hierarchy_config": VALID_HIERARCHY,
                },
                format="json",
            )
        assert resp.status_code == 200
        assert len(resp.data["results"]) == 1
        assert resp.data["results"][0]["cnr_number"] == "MHAU019999992024"
        # Provider called with a NAME, not a bar code.
        call_kwargs = mock_get_provider.return_value.search_by_advocate.call_args.kwargs
        assert call_kwargs["advocate_name"] == "Suresh"
        assert call_kwargs["bar_code"] == ""

    def test_valid_bar_code_search(self, client_a):
        with patch("core.views.advocate_search.get_provider") as mock_get_provider:
            mock_get_provider.return_value.search_by_advocate.return_value = [_case_info()]
            resp = client_a.post(
                "/api/cases/search-advocate/",
                {
                    "name_or_bar_code": "MAH/1234/2015",
                    "court_type": "district",
                    "hierarchy_config": VALID_HIERARCHY,
                },
                format="json",
            )
        assert resp.status_code == 200
        call_kwargs = mock_get_provider.return_value.search_by_advocate.call_args.kwargs
        assert call_kwargs["bar_code"] == "MAH/1234/2015"
        assert call_kwargs["advocate_name"] == ""

    def test_name_too_short_rejected(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "AB", "court_type": "district", "hierarchy_config": VALID_HIERARCHY},
            format="json",
        )
        assert resp.status_code == 400

    def test_missing_hierarchy_rejected(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "hierarchy_config": {}},
            format="json",
        )
        assert resp.status_code == 400

    def test_high_court_not_yet_supported(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "high_court", "hierarchy_config": VALID_HIERARCHY},
            format="json",
        )
        assert resp.status_code == 400

    def test_captcha_failure_is_retryable_not_500(self, client_a):
        with patch("core.views.advocate_search.get_provider") as mock_get_provider:
            mock_get_provider.return_value.search_by_advocate.side_effect = CaptchaSolveError("nope")
            resp = client_a.post(
                "/api/cases/search-advocate/",
                {"name_or_bar_code": "Suresh", "court_type": "district", "hierarchy_config": VALID_HIERARCHY},
                format="json",
            )
        assert resp.status_code == 502
        assert resp.data["code"] == "captcha_failed"

    def test_portal_timeout_is_retryable_not_500(self, client_a):
        with patch("core.views.advocate_search.get_provider") as mock_get_provider:
            mock_get_provider.return_value.search_by_advocate.side_effect = CourtPortalError("timed out")
            resp = client_a.post(
                "/api/cases/search-advocate/",
                {"name_or_bar_code": "Suresh", "court_type": "district", "hierarchy_config": VALID_HIERARCHY},
                format="json",
            )
        assert resp.status_code == 502

    def test_search_saves_preference(self, client_a, user_a):
        with patch("core.views.advocate_search.get_provider") as mock_get_provider:
            mock_get_provider.return_value.search_by_advocate.return_value = []
            client_a.post(
                "/api/cases/search-advocate/",
                {"name_or_bar_code": "Suresh", "court_type": "district", "hierarchy_config": VALID_HIERARCHY},
                format="json",
            )
        pref = AdvocateSearchPreference.objects.get(owner=user_a)
        assert pref.hierarchy_config == VALID_HIERARCHY

    def test_requires_authentication(self):
        anon = APIClient()
        resp = anon.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "hierarchy_config": VALID_HIERARCHY},
            format="json",
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# run_advocate_import (service-level)
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
# AdvocateSearchImportView / AdvocateSearchImportStatusView
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
        selected = [{"cnr_number": f"CNR{i:013d}"} for i in range(26)]
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
    def test_preference_scoped_to_owner(self, client_a, client_b, user_a, user_b):
        AdvocateSearchPreference.objects.create(
            owner=user_a, court_type="district", hierarchy_config=VALID_HIERARCHY
        )
        resp = client_b.get("/api/cases/search-advocate/preference/")
        assert resp.status_code == 200
        assert resp.data is None

        resp = client_a.get("/api/cases/search-advocate/preference/")
        assert resp.status_code == 200
        assert resp.data["hierarchy_config"] == VALID_HIERARCHY
