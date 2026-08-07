"""Regression tests for the post-advocate-import tracking 502.

Every case here is built with the shape core/services/advocate_import.py
actually produces -- NOT the manually-created shape the older tests use.
The difference that matters: an imported case is created with
tracking_enabled=True and tracking_config={"court_type", "cnr"} but with
cnr_number left UNSET (the fetch is supposed to populate it), so a case
whose import fetch failed looks different from any manually-tracked case.

Three distinct defects are covered:
  1. The import endpoint accepted any court_type, producing cases whose
     every later refresh raised ValueError out of the provider.
  2. run_advocate_import only isolated CourtDataError, so one unmapped
     exception killed the whole batch.
  3. The refresh view let unmapped exceptions escape entirely.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Case, ProcessingJob
from core.services.advocate_import import run_advocate_import
from core.services.court_data import CaptchaSolveError, CourtDataError, CourtPortalError
from core.services.court_data.models import CourtCaseData
from core.services.court_tracking import (
    InvalidTrackingConfigError,
    refresh_case_tracking,
)

# One real row from a live advocate_search job payload (local job 16).
SEARCH_RESULT = {
    "cnr_number": "TSWR000000792000",
    "case_number": "AS/35/2000",
    "case_type": "AS",
    "petitioner": "Mohd.Naseeruddin",
    "respondent": "Mohd.Asgar Ali",
    "court_name": "",
    "filing_number": "",
    "registration_number": "",
    "registration_date": None,
    "judges": [],
    "status": "",
    "next_hearing_date": None,
}


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="import-advocate", password="pass-123")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


def imported_case(owner, *, cnr="TSWR000000792000", court_type="district", number="AS/35/2000"):
    """A Case exactly as run_advocate_import() creates it.

    Note cnr_number is deliberately NOT set: the import relies on the
    fetch to populate it, so a case whose fetch failed has tracking
    enabled and a config but no CNR column -- a shape manual setup never
    produces.
    """
    return Case.objects.create(
        owner=owner,
        case_number=number,
        title=number,
        client_name="",
        court_type=court_type,
        tracking_config={"court_type": court_type, "cnr": cnr},
        tracking_enabled=True,
    )


class TestImportCourtTypeValidation:
    """Defect 1: the import endpoint validated nothing."""

    @pytest.mark.parametrize("bad", ["banana", "High Court", "District", "high court", "0"])
    def test_invalid_court_type_is_rejected(self, api, bad, db):
        response = api.post(
            "/api/cases/search-advocate/import/",
            {"court_type": bad, "selected": [SEARCH_RESULT]},
            format="json",
        )
        assert response.status_code == 400
        assert "court_type" in str(response.data).lower()
        assert not ProcessingJob.objects.filter(job_type="advocate_import").exists()

    def test_invalid_per_item_court_type_is_rejected(self, api, db):
        """The per-item override was the sneakier path -- the top-level
        value could be valid while an item smuggled in anything."""
        response = api.post(
            "/api/cases/search-advocate/import/",
            {
                "court_type": "district",
                "selected": [{**SEARCH_RESULT, "court_type": "banana"}],
            },
            format="json",
        )
        assert response.status_code == 400
        assert not ProcessingJob.objects.filter(job_type="advocate_import").exists()

    @pytest.mark.parametrize("good", ["district", "high_court"])
    def test_valid_court_types_are_accepted(self, api, good, db):
        response = api.post(
            "/api/cases/search-advocate/import/",
            {"court_type": good, "selected": [SEARCH_RESULT]},
            format="json",
        )
        assert response.status_code == 202

    def test_omitted_court_type_still_defaults_to_district(self, api, db):
        response = api.post(
            "/api/cases/search-advocate/import/",
            {"selected": [SEARCH_RESULT]},
            format="json",
        )
        assert response.status_code == 202
        job = ProcessingJob.objects.get(job_type="advocate_import")
        assert job.payload["selected"][0]["court_type"] == "district"


@pytest.mark.django_db
class TestImportFailureIsolation:
    """Defect 2: one unmapped exception killed the whole batch."""

    def _job(self, owner, items):
        return ProcessingJob.objects.create(
            owner=owner,
            job_type="advocate_import",
            status="running",
            payload={"selected": items, "advocate_name": "Test Advocate", "bar_code": ""},
        )

    @patch("core.services.court_tracking.get_provider")
    def test_unmapped_exception_does_not_kill_the_batch(self, get_provider, advocate):
        """A ValueError on case 2 must not lose cases 3 and 4."""
        items = [
            {**SEARCH_RESULT, "cnr_number": f"TSWR00000079200{i}",
             "case_number": f"AS/3{i}/2000", "court_type": "district"}
            for i in range(4)
        ]
        job = self._job(advocate, items)

        provider = MagicMock()
        provider.fetch_case.side_effect = [
            CourtCaseData(cnr="TSWR000000792000"),
            ValueError("Unknown court_type: 'banana'"),
            CourtCaseData(cnr="TSWR000000792002"),
            CourtCaseData(cnr="TSWR000000792003"),
        ]
        get_provider.return_value = provider

        run_advocate_import(job)  # must not raise

        job.refresh_from_db()
        assert len(job.payload["created"]) == 3
        assert len(job.payload["failed"]) == 1
        assert "ValueError" in job.payload["failed"][0]["error"]

    @patch("core.services.court_tracking.get_provider")
    def test_court_data_error_is_still_isolated(self, get_provider, advocate):
        """The pre-existing CourtDataError path must keep working."""
        items = [
            {**SEARCH_RESULT, "cnr_number": f"TSWR00000079200{i}",
             "case_number": f"AS/4{i}/2000", "court_type": "district"}
            for i in range(2)
        ]
        job = self._job(advocate, items)

        provider = MagicMock()
        provider.fetch_case.side_effect = [
            CourtDataError("case not found"),
            CourtCaseData(cnr="TSWR000000792001"),
        ]
        get_provider.return_value = provider

        run_advocate_import(job)

        job.refresh_from_db()
        assert len(job.payload["created"]) == 1
        assert len(job.payload["failed"]) == 1


@pytest.mark.django_db
class TestRefreshOnImportedCase:
    """Defect 3 + the court_type fallback, on the imported case shape."""

    @patch("core.services.court_tracking.get_provider")
    def test_unmapped_exception_returns_a_response_not_a_crash(
        self, get_provider, api, advocate
    ):
        case = imported_case(advocate)
        provider = MagicMock()
        provider.fetch_case.side_effect = ValueError("Unknown court_type: None")
        get_provider.return_value = provider

        # Previously this propagated out of the view entirely.
        response = api.post(f"/api/cases/{case.id}/tracking/refresh/", {}, format="json")
        assert response.status_code == 500
        assert response.data["code"] == "refresh_failed"

    @patch("core.services.court_tracking.get_provider")
    def test_transport_error_returns_a_response_not_a_crash(
        self, get_provider, api, advocate
    ):
        case = imported_case(advocate)
        provider = MagicMock()
        provider.fetch_case.side_effect = TimeoutError("read timeout")
        get_provider.return_value = provider

        response = api.post(f"/api/cases/{case.id}/tracking/refresh/", {}, format="json")
        assert response.status_code == 500
        assert response.data["code"] == "refresh_failed"

    @patch("core.services.court_tracking.get_provider")
    def test_missing_court_type_falls_back_to_the_case_column(
        self, get_provider, advocate
    ):
        """A config that lost its court_type is still refreshable when the
        Case row carries a valid one -- the two are written together."""
        case = imported_case(advocate)
        case.tracking_config = {"cnr": "TSWR000000792000"}  # no court_type
        case.court_type = "district"
        case.save()

        provider = MagicMock()
        provider.fetch_case.return_value = CourtCaseData(cnr="TSWR000000792000")
        get_provider.return_value = provider

        refresh_case_tracking(case, force=True)

        dispatched = provider.fetch_case.call_args[0][0]
        assert dispatched["court_type"] == "district"

    @patch("core.services.court_tracking.get_provider")
    def test_invalid_court_type_falls_back_to_the_case_column(
        self, get_provider, advocate
    ):
        case = imported_case(advocate, court_type="district")
        case.tracking_config = {"cnr": "TSWR000000792000", "court_type": "banana"}
        case.save()

        provider = MagicMock()
        provider.fetch_case.return_value = CourtCaseData(cnr="TSWR000000792000")
        get_provider.return_value = provider

        refresh_case_tracking(case, force=True)
        assert provider.fetch_case.call_args[0][0]["court_type"] == "district"

    @patch("core.services.court_tracking.get_provider")
    def test_no_usable_court_type_anywhere_raises_rather_than_guessing(
        self, get_provider, advocate
    ):
        """Defaulting to "district" would fetch the wrong portal and could
        bind the case to a different real case sharing the number."""
        case = imported_case(advocate)
        case.tracking_config = {"cnr": "TSWR000000792000", "court_type": "banana"}
        case.court_type = None
        case.save()

        with pytest.raises(InvalidTrackingConfigError):
            refresh_case_tracking(case, force=True)

        get_provider.return_value.fetch_case.assert_not_called()

    @patch("core.services.court_tracking.get_provider")
    def test_unusable_court_type_is_an_actionable_400(self, get_provider, api, advocate):
        case = imported_case(advocate)
        case.tracking_config = {"cnr": "TSWR000000792000", "court_type": ""}
        case.court_type = None
        case.save()

        response = api.post(f"/api/cases/{case.id}/tracking/refresh/", {}, format="json")
        assert response.status_code == 400
        assert response.data["code"] == "invalid_config"

    @patch("core.services.court_tracking.get_provider")
    def test_portal_errors_still_map_to_502(self, get_provider, api, advocate):
        """Documents the 502 that IS by design: Django returns it itself,
        it is not a crashed worker. Kept as a test so the next person
        reading a 502 in the network log knows which kind it is."""
        for exc in (CaptchaSolveError("captcha"), CourtPortalError("portal down")):
            case = imported_case(advocate, number=f"AS/9{id(exc) % 100}/2000")
            provider = MagicMock()
            provider.fetch_case.side_effect = exc
            get_provider.return_value = provider

            response = api.post(f"/api/cases/{case.id}/tracking/refresh/", {}, format="json")
            assert response.status_code == 502

    @patch("core.services.court_tracking.get_provider")
    def test_healthy_imported_case_refreshes(self, get_provider, api, advocate):
        case = imported_case(advocate)
        provider = MagicMock()
        provider.fetch_case.return_value = CourtCaseData(cnr="TSWR000000792000")
        get_provider.return_value = provider

        response = api.post(f"/api/cases/{case.id}/tracking/refresh/", {}, format="json")
        assert response.status_code == 200


@pytest.mark.django_db
class TestSearchStatusPayloadCap:
    """The 502 mechanism itself: an uncapped result set."""

    def _job(self, owner, n):
        return ProcessingJob.objects.create(
            owner=owner,
            job_type="advocate_search",
            status="succeeded",
            payload={
                "results": [
                    {**SEARCH_RESULT, "cnr_number": f"TSWR{i:012d}"} for i in range(n)
                ]
            },
        )

    def test_large_result_set_is_capped(self, api, advocate):
        from core.views.advocate_search import MAX_RESULTS_IN_RESPONSE

        job = self._job(advocate, MAX_RESULTS_IN_RESPONSE + 250)
        response = api.get(f"/api/cases/search-advocate/{job.id}/")

        assert response.status_code == 200
        assert len(response.data["results"]) == MAX_RESULTS_IN_RESPONSE
        assert response.data["results_total"] == MAX_RESULTS_IN_RESPONSE + 250
        assert response.data["results_truncated"] is True

    def test_small_result_set_is_untouched(self, api, advocate):
        job = self._job(advocate, 12)
        response = api.get(f"/api/cases/search-advocate/{job.id}/")

        assert len(response.data["results"]) == 12
        assert response.data["results_total"] == 12
        assert response.data["results_truncated"] is False

    def test_response_size_stays_bounded(self, api, advocate):
        """The actual regression: a real job held 130,032 results, which
        serialised to ~38.7 MB per poll -- and the frontend polls every
        1.5s. That is what exhausted the 2 gunicorn workers on a 1 GB
        t3.micro and turned unrelated requests into 502s."""
        import json

        job = self._job(advocate, 50_000)
        response = api.get(f"/api/cases/search-advocate/{job.id}/")

        size_mb = len(json.dumps(response.data, default=str)) / 1024 / 1024
        assert size_mb < 1.0, f"status response is {size_mb:.1f} MB"
        assert response.data["results_total"] == 50_000
