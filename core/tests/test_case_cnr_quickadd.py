"""Tests for the "Track by CNR" quick-add flow on the manual case entry
page (core/views/case_tracking.py's CaseCnrLookupView/CaseCnrCreateView,
core/services/court_tracking.py's preview_case_creation_from_cnr/
create_case_from_cnr_preview).

Covers: successful fetch+create, same-user CNR duplicate blocked (both at
lookup time and at create time), cross-user case_number collision handled
gracefully (not a 500), and a regression check that the existing
fully-manual entry path and the per-case "link CNR later" preview/confirm
flow still work unchanged after the confirm_case_tracking() refactor.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import AdvocateProfile, Case
from core.services.court_data import CaseNotFoundError
from core.services.court_data.models import CourtCaseData, HearingRecord

CNR = "MHAU019999992024"
OTHER_CNR = "DLHC012345678920"


def _authed_client(user):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def advocate():
    return User.objects.create_user(username="cnr-quickadd-advocate", password="pass-123")


@pytest.fixture
def other_advocate():
    return User.objects.create_user(username="cnr-quickadd-other", password="pass-123")


@pytest.fixture
def api(advocate):
    return _authed_client(advocate)


@pytest.fixture
def other_api(other_advocate):
    return _authed_client(other_advocate)


def _fake_case_data(cnr=CNR, **overrides):
    defaults = dict(
        cnr=cnr,
        case_status="CASE PENDING",
        case_stage="Arguments",
        court_name="District Court, Aurangabad",
        petitioner="Ramesh Kumar",
        respondent="TSSPDCL",
        party_advocate_data={
            "petitioner_advocates": ["Advocate A. Sharma"],
            "respondent_advocates": ["Advocate B. Rao"],
        },
        hearing_history=[HearingRecord(hearing_date=None)],
    )
    defaults.update(overrides)
    return CourtCaseData(**defaults)


@pytest.mark.django_db
class TestCnrLookupAndCreateSuccess:
    @patch("core.services.court_tracking.get_provider")
    def test_fetch_prefills_and_create_persists_case_with_tracking(self, get_provider, api, advocate):
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data()
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")
        assert lookup.status_code == 200
        assert lookup.data["case_number"] == CNR
        assert lookup.data["title"] == CNR
        assert lookup.data["petitioner"] == "Ramesh Kumar"
        assert lookup.data["respondent"] == "TSSPDCL"
        assert "preview_token" in lookup.data

        create = api.post(
            "/api/cases/cnr-lookup/create/",
            {
                "preview_token": lookup.data["preview_token"],
                "case_number": CNR,
                "title": "Ramesh Kumar vs TSSPDCL",
                "user_party_role": "petitioner",
            },
            format="json",
        )
        assert create.status_code == 201
        assert create.data["case_number"] == CNR
        assert create.data["title"] == "Ramesh Kumar vs TSSPDCL"
        assert create.data["cnr_number"] == CNR
        assert create.data["tracking_enabled"] is True
        assert create.data["fetch_status"] == "success"

        case = Case.objects.get(case_number=CNR)
        assert case.owner_id == advocate.id
        assert case.cnr_number == CNR
        assert case.court_type in ("district", "high_court")
        assert case.tracking_config == {"cnr": CNR, "court_type": case.court_type}

    @patch("core.services.court_tracking.get_provider")
    def test_party_role_detected_from_requesting_users_advocate_profile(self, get_provider, api, advocate):
        AdvocateProfile.objects.create(
            owner=advocate, letterhead_name="Advocate A. Sharma", bar_registration_number="AP/1234/2015"
        )
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data()
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")
        assert lookup.status_code == 200
        # "Advocate A. Sharma" matches the petitioner_advocates entry above.
        assert lookup.data["user_party_role"] == "petitioner"
        assert lookup.data["opposing_party"] == "TSSPDCL"

    @patch("core.services.court_tracking.get_provider")
    def test_court_type_auto_detected_when_omitted(self, get_provider, api):
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data(cnr=OTHER_CNR)
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": OTHER_CNR}, format="json")
        assert lookup.status_code == 200
        assert lookup.data["court_type"] == "high_court"
        assert lookup.data["court_type_detected"] is True
        provider.fetch_case_by_cnr.assert_called_once_with(OTHER_CNR, "high_court")

    def test_invalid_cnr_format_rejected(self, api):
        resp = api.post("/api/cases/cnr-lookup/", {"cnr": "too-short"}, format="json")
        assert resp.status_code == 400

    @patch("core.services.court_tracking.get_provider")
    def test_not_found_surfaces_existing_error_taxonomy(self, get_provider, api):
        provider = MagicMock()
        provider.fetch_case_by_cnr.side_effect = CaseNotFoundError("not on District Courts")
        get_provider.return_value = provider

        resp = api.post("/api/cases/cnr-lookup/", {"cnr": CNR, "court_type": "district"}, format="json")
        assert resp.status_code == 400
        assert resp.data["code"] == "case_not_found"


@pytest.mark.django_db
class TestSameUserCnrDuplicate:
    @patch("core.services.court_tracking.get_provider")
    def test_lookup_blocks_before_hitting_portal(self, get_provider, api, advocate):
        existing = Case.objects.create(
            owner=advocate, case_number="EXISTING-1", title="Already tracked", client_name="",
            cnr_number=CNR, tracking_enabled=True,
        )
        provider = MagicMock()
        get_provider.return_value = provider

        resp = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")

        assert resp.status_code == 409
        assert resp.data["code"] == "duplicate_cnr"
        assert resp.data["case_id"] == existing.id
        assert resp.data["case_number"] == "EXISTING-1"
        provider.fetch_case_by_cnr.assert_not_called()

    @patch("core.services.court_tracking.get_provider")
    def test_create_blocks_on_race_between_preview_and_confirm(self, get_provider, api, advocate):
        """The CNR wasn't a duplicate at preview time, but another request
        (e.g. a second browser tab) created a case with it before confirm
        -- create_case_from_cnr_preview's own re-check must catch this,
        not just the lookup-time check."""
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data()
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")
        assert lookup.status_code == 200

        existing = Case.objects.create(
            owner=advocate, case_number="RACE-WINNER", title="Got there first", client_name="",
            cnr_number=CNR, tracking_enabled=True,
        )

        create = api.post(
            "/api/cases/cnr-lookup/create/",
            {"preview_token": lookup.data["preview_token"], "case_number": CNR, "title": CNR},
            format="json",
        )

        assert create.status_code == 409
        assert create.data["code"] == "duplicate_cnr"
        assert create.data["case_id"] == existing.id
        # No second case was created for this CNR.
        assert Case.objects.filter(owner=advocate, cnr_number=CNR).count() == 1


@pytest.mark.django_db
class TestCrossUserCaseNumberConflict:
    @patch("core.services.court_tracking.get_provider")
    def test_case_number_collision_with_another_owner_is_graceful_not_500(
        self, get_provider, api, advocate, other_advocate
    ):
        Case.objects.create(
            owner=other_advocate, case_number="SHARED-NUMBER", title="Other advocate's case", client_name="",
        )
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data()
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")
        assert lookup.status_code == 200

        create = api.post(
            "/api/cases/cnr-lookup/create/",
            {
                "preview_token": lookup.data["preview_token"],
                "case_number": "SHARED-NUMBER",
                "title": "My version of this case",
            },
            format="json",
        )

        assert create.status_code == 400
        assert "case_number" in create.data
        assert "already tracked by another user in the system" in create.data["case_number"][0]
        # Nothing was created under this owner for this CNR -- a failed
        # create must not leave a half-applied row behind.
        assert not Case.objects.filter(owner=advocate, cnr_number=CNR).exists()


@pytest.mark.django_db
class TestExistingFlowsUnchanged:
    def test_fully_manual_entry_still_works(self, api):
        resp = api.post(
            "/api/cases/",
            {"case_number": "MANUAL-1", "title": "Typed in by hand"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["cnr_number"] is None
        assert resp.data["tracking_enabled"] is False

    @patch("core.services.court_tracking.get_provider")
    def test_link_cnr_later_flow_still_works_after_refactor(self, get_provider, api, advocate):
        """Regression guard for the confirm_case_tracking()/
        _finalize_confirmed_fetch() extraction: the existing per-case
        preview -> confirm flow (case detail page's "link CNR later")
        must behave identically to before."""
        case = Case.objects.create(
            owner=advocate, case_number="LINK-LATER-1", title="Link later case", client_name="",
        )
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data(cnr=OTHER_CNR)
        get_provider.return_value = provider

        preview = api.post(
            f"/api/cases/{case.id}/tracking/preview/", {"cnr": OTHER_CNR}, format="json"
        )
        assert preview.status_code == 200

        confirm = api.post(
            f"/api/cases/{case.id}/tracking/confirm/",
            {"preview_token": preview.data["preview_token"]},
            format="json",
        )
        assert confirm.status_code == 201

        case.refresh_from_db()
        assert case.cnr_number == OTHER_CNR
        assert case.tracking_enabled is True
        assert case.fetch_status == "success"

    def test_case_number_search_field_present_on_serialized_case(self, api):
        """cnr_number must be present on the serialized Case for the
        frontend's client-side Cases-tab search to be able to match on it."""
        resp = api.post(
            "/api/cases/",
            {"case_number": "SEARCH-FIELD-CHECK", "title": "x"},
            format="json",
        )
        assert resp.status_code == 201
        assert "cnr_number" in resp.data
