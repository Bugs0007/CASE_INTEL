"""CNR-only court-type auto-detection (core/services/court_tracking.py).

Case tracking setup used to require the user to pick District Court vs.
High Court before searching by CNR, even though a CNR alone is often
enough to tell which portal it belongs to. Covers:

  1. _guess_court_type_from_cnr(): the CNR-prefix guess itself, backed by
     bharat_courts' verified HC/SCI prefix table -- not a guess invented
     in this codebase.
  2. _fetch_by_cnr_auto(): try-the-guess-first, fall back to the other
     court type ONLY on a genuine CaseNotFoundError, and never fall back
     on CaptchaSolveError/CourtPortalError (those mean "couldn't check",
     not "not there").
  3. The preview API end-to-end: a CNR-only body with no court_type is
     accepted, the resolved court_type comes back in the response, and
     confirming persists it onto the Case so refreshes never re-detect.
"""

from unittest.mock import MagicMock, call, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Case
from core.services.court_data import CaptchaSolveError, CaseNotFoundError, CourtPortalError
from core.services.court_data.models import CourtCaseData
from core.services.court_tracking import _fetch_by_cnr_auto, _guess_court_type_from_cnr

# A CNR whose 4-letter prefix ("DLHC") is in bharat_courts' verified HC
# table -- Delhi High Court.
HC_CNR = "DLHC012345678920"
assert len(HC_CNR) == 16

# A CNR whose prefix ("MHAU", Aurangabad district establishment) is NOT an
# HC/SCI prefix -- same fixture value used in test_advocate_search.py.
DISTRICT_CNR = "MHAU019999992024"
assert len(DISTRICT_CNR) == 16


# ---------------------------------------------------------------------------
# 1. CNR-format detection
# ---------------------------------------------------------------------------


class TestGuessCourtTypeFromCnr:
    def test_known_high_court_prefix_is_detected(self):
        assert _guess_court_type_from_cnr(HC_CNR) == "high_court"

    def test_district_style_prefix_returns_none_not_district(self):
        """A non-HC prefix must NOT be reported as "district confirmed" --
        the table has no district-court entries to check against, so the
        only honest answer is "unknown"."""
        assert _guess_court_type_from_cnr(DISTRICT_CNR) is None

    def test_malformed_cnr_returns_none_without_raising(self):
        assert _guess_court_type_from_cnr("XX") is None
        assert _guess_court_type_from_cnr("") is None


# ---------------------------------------------------------------------------
# 2. Fetch-with-fallback orchestration
# ---------------------------------------------------------------------------


class TestFetchByCnrAuto:
    def test_first_try_success_makes_only_one_call(self):
        provider = MagicMock()
        data = CourtCaseData(cnr=HC_CNR)
        provider.fetch_case_by_cnr.return_value = data

        result_data, court_type = _fetch_by_cnr_auto(provider, HC_CNR)

        assert result_data is data
        assert court_type == "high_court"
        provider.fetch_case_by_cnr.assert_called_once_with(HC_CNR, "high_court")

    def test_fallback_success_tries_the_other_type_in_order(self):
        """No usable guess (DISTRICT_CNR's prefix isn't a known HC one) --
        must try district first, then high_court, and succeed on the
        second call."""
        provider = MagicMock()
        data = CourtCaseData(cnr=DISTRICT_CNR)
        provider.fetch_case_by_cnr.side_effect = [
            CaseNotFoundError("not on District Courts"),
            data,
        ]

        result_data, court_type = _fetch_by_cnr_auto(provider, DISTRICT_CNR)

        assert result_data is data
        assert court_type == "high_court"
        assert provider.fetch_case_by_cnr.call_args_list == [
            call(DISTRICT_CNR, "district"),
            call(DISTRICT_CNR, "high_court"),
        ]

    def test_guessed_type_that_turns_out_wrong_still_falls_back(self):
        """HC_CNR's prefix suggests high_court, but if the portal genuinely
        doesn't have it, fall back to district rather than giving up."""
        provider = MagicMock()
        data = CourtCaseData(cnr=HC_CNR)
        provider.fetch_case_by_cnr.side_effect = [
            CaseNotFoundError("not on HC Services"),
            data,
        ]

        result_data, court_type = _fetch_by_cnr_auto(provider, HC_CNR)

        assert result_data is data
        assert court_type == "district"
        assert provider.fetch_case_by_cnr.call_args_list == [
            call(HC_CNR, "high_court"),
            call(HC_CNR, "district"),
        ]

    def test_both_genuinely_not_found_raises_specific_combined_error(self):
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = [
            CaseNotFoundError("not on District Courts"),
            CaseNotFoundError("not on HC Services"),
        ]

        with pytest.raises(CaseNotFoundError) as exc_info:
            _fetch_by_cnr_auto(provider, DISTRICT_CNR)

        message = str(exc_info.value)
        assert "District Court" in message
        assert "High Court" in message
        assert provider.fetch_case_by_cnr.call_count == 2

    def test_captcha_failure_does_not_trigger_fallback(self):
        """A CAPTCHA failure means "couldn't check", not "not there" --
        falling back would both mislead (a solve failure looks identical
        to "not filed here") and double the CAPTCHA cost for nothing."""
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = CaptchaSolveError("captcha failed")

        with pytest.raises(CaptchaSolveError):
            _fetch_by_cnr_auto(provider, DISTRICT_CNR)

        provider.fetch_case_by_cnr.assert_called_once()

    def test_portal_error_does_not_trigger_fallback(self):
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = CourtPortalError("portal down")

        with pytest.raises(CourtPortalError):
            _fetch_by_cnr_auto(provider, DISTRICT_CNR)

        provider.fetch_case_by_cnr.assert_called_once()

    def test_portal_error_on_second_attempt_does_not_mask_as_not_found(self):
        """The first portal genuinely doesn't have it; the second is
        unreachable. The caller must see CourtPortalError, not a
        misleading "not found in either"."""
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = [
            CaseNotFoundError("not on District Courts"),
            CourtPortalError("HC Services unreachable"),
        ]

        with pytest.raises(CourtPortalError):
            _fetch_by_cnr_auto(provider, DISTRICT_CNR)

        assert provider.fetch_case_by_cnr.call_count == 2


# ---------------------------------------------------------------------------
# 3. Preview/confirm API, end-to-end
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="cnr-detect-advocate", password="pass-123")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.fixture
def case(advocate):
    return Case.objects.create(
        owner=advocate,
        case_number="CNR-DETECT-1",
        title="CNR Detect Test",
        client_name="",
    )


@pytest.mark.django_db
class TestCnrOnlyPreviewApi:
    @patch("core.services.court_tracking.get_provider")
    def test_cnr_only_body_is_accepted_and_reports_detected_type(
        self, get_provider, api, case
    ):
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = CourtCaseData(cnr=HC_CNR)
        get_provider.return_value = provider

        response = api.post(
            f"/api/cases/{case.id}/tracking/preview/", {"cnr": HC_CNR}, format="json"
        )

        assert response.status_code == 200
        assert response.data["court_type"] == "high_court"
        assert response.data["court_type_detected"] is True
        provider.fetch_case_by_cnr.assert_called_once_with(HC_CNR, "high_court")

    @patch("core.services.court_tracking.get_provider")
    def test_explicit_court_type_skips_detection(self, get_provider, api, case):
        provider = MagicMock()
        provider.fetch_case.return_value = CourtCaseData(cnr=HC_CNR)
        get_provider.return_value = provider

        response = api.post(
            f"/api/cases/{case.id}/tracking/preview/",
            {"cnr": HC_CNR, "court_type": "district"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["court_type"] == "district"
        assert response.data["court_type_detected"] is False
        provider.fetch_case_by_cnr.assert_not_called()
        provider.fetch_case.assert_called_once()

    @patch("core.services.court_tracking.get_provider")
    def test_confirm_persists_detected_court_type_on_the_case(
        self, get_provider, api, case
    ):
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = [
            CaseNotFoundError("not on District Courts"),
            CourtCaseData(cnr=DISTRICT_CNR),
        ]
        get_provider.return_value = provider

        preview = api.post(
            f"/api/cases/{case.id}/tracking/preview/", {"cnr": DISTRICT_CNR}, format="json"
        )
        assert preview.status_code == 200
        assert preview.data["court_type"] == "high_court"

        confirm = api.post(
            f"/api/cases/{case.id}/tracking/confirm/",
            {"preview_token": preview.data["preview_token"]},
            format="json",
        )
        assert confirm.status_code == 201

        case.refresh_from_db()
        assert case.court_type == "high_court"
        assert case.tracking_config["court_type"] == "high_court"

    @patch("core.services.court_tracking.get_provider")
    def test_not_found_in_either_court_gives_specific_message(
        self, get_provider, api, case
    ):
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = [
            CaseNotFoundError("not on District Courts"),
            CaseNotFoundError("not on HC Services"),
        ]
        get_provider.return_value = provider

        response = api.post(
            f"/api/cases/{case.id}/tracking/preview/", {"cnr": DISTRICT_CNR}, format="json"
        )

        assert response.status_code == 400
        assert response.data["code"] == "case_not_found"
        assert "District Court" in response.data["detail"]
        assert "High Court" in response.data["detail"]

    @patch("core.services.court_tracking.get_provider")
    def test_captcha_failure_surfaces_as_502_without_a_second_attempt(
        self, get_provider, api, case
    ):
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = CaptchaSolveError("captcha failed")
        get_provider.return_value = provider

        response = api.post(
            f"/api/cases/{case.id}/tracking/preview/", {"cnr": DISTRICT_CNR}, format="json"
        )

        assert response.status_code == 502
        assert response.data["code"] == "captcha_failed"
        provider.fetch_case_by_cnr.assert_called_once()

    def test_cnr_body_with_no_court_type_passes_validation(self, api, case):
        """Regression guard for the view-layer validator: a CNR-only body
        used to be rejected outright for missing court_type."""
        with patch("core.services.court_tracking.get_provider") as get_provider:
            provider = MagicMock()
            provider.fetch_case_by_cnr.return_value = CourtCaseData(cnr=DISTRICT_CNR)
            get_provider.return_value = provider

            response = api.post(
                f"/api/cases/{case.id}/tracking/preview/",
                {"cnr": DISTRICT_CNR},
                format="json",
            )
        assert response.status_code != 400

    def test_cascade_shape_still_requires_court_type(self, api, case):
        response = api.post(
            f"/api/cases/{case.id}/tracking/preview/",
            {
                "case_type": "AS",
                "case_number": "35",
                "year": "2020",
                "state_code": "29",
                "dist_code": "2",
                "court_complex_code": "1",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "court_type" in response.data["detail"]
