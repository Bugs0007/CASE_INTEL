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


REGISTRATION_NUMBER = "WP/23998/2026"


@pytest.mark.django_db
class TestRegistrationNumberUsedAsCaseNumber:
    """Regression coverage for a live-verified bug: preview_case_creation_
    from_cnr() was unconditionally setting case_number/title to the CNR
    string, even when eCourts' case-history response actually carried a
    real registration number (e.g. "WP /23998/2026") -- the CNR is not a
    human-recognizable case number, and the cause-list matcher can't match
    a case against real cause-list entries using a CNR where it expects a
    parseable case-number format.

    Root cause was two layers deep: CourtCaseData had no field to carry a
    registration number at all, so _DETAIL_LABELS (core/services/
    court_data/ecourts_parsing.py) never captured it out of the case-
    history HTML in the first place -- it was discarded before
    preview_case_creation_from_cnr ever saw it, not just mis-prioritized
    there. Fixed by adding CourtCaseData.registration_number, mapping
    "registration no" in _DETAIL_LABELS, and using
    `data.registration_number or cnr` (CNR only as the last resort) when
    building the preview response.
    """

    @patch("core.services.court_tracking.get_provider")
    def test_lookup_uses_fetched_registration_number_not_cnr(self, get_provider, api):
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data(
            registration_number=REGISTRATION_NUMBER
        )
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")

        assert lookup.status_code == 200
        assert lookup.data["case_number"] == REGISTRATION_NUMBER
        assert lookup.data["title"] == REGISTRATION_NUMBER
        assert lookup.data["case_number"] != CNR

    @patch("core.services.court_tracking.get_provider")
    def test_create_persists_fetched_registration_number_as_case_number(self, get_provider, api):
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data(
            registration_number=REGISTRATION_NUMBER
        )
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")
        assert lookup.status_code == 200

        # Submit exactly what the form was pre-filled with -- the common
        # path where the advocate doesn't touch case_number/title before
        # confirming.
        create = api.post(
            "/api/cases/cnr-lookup/create/",
            {
                "preview_token": lookup.data["preview_token"],
                "case_number": lookup.data["case_number"],
                "title": lookup.data["title"],
            },
            format="json",
        )

        assert create.status_code == 201
        assert create.data["case_number"] == REGISTRATION_NUMBER

        case = Case.objects.get(cnr_number=CNR)
        assert case.case_number == REGISTRATION_NUMBER
        assert case.case_number != case.cnr_number

    @patch("core.services.court_tracking.get_provider")
    def test_lookup_falls_back_to_cnr_only_when_no_registration_number(self, get_provider, api):
        """The CNR fallback is still correct for the rare record types
        eCourts returns with no Registration Number row at all."""
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _fake_case_data(registration_number="")
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR}, format="json")

        assert lookup.status_code == 200
        assert lookup.data["case_number"] == CNR
        assert lookup.data["title"] == CNR


class TestParseCaseHistoryHtmlRegistrationNumber:
    """Root-cause-layer coverage: the case-history HTML parser itself must
    capture the Registration Number row -- see the module-level docstring
    on TestRegistrationNumberUsedAsCaseNumber for why this matters."""

    def test_registration_no_label_is_captured(self):
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr><th>Registration No</th><td>WP/23998/2026</td></tr>
          <tr><th>Case Status</th><td>CASE PENDING</td></tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == "WP/23998/2026"

    def test_registration_number_label_variant_is_also_captured(self):
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr><th>Registration Number</th><td>OS/145/2025</td></tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == "OS/145/2025"

    def test_missing_registration_row_leaves_field_blank(self):
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr><th>Case Status</th><td>CASE PENDING</td></tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == ""

    def test_registration_date_row_is_not_mistaken_for_registration_number(self):
        """eCourts case-history pages also have a separate "Registration
        Date" row -- a bare "registration" prefix key would wrongly
        capture a date string into this field."""
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr><th>Registration Date</th><td>12-03-2026</td></tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == ""


class TestParseCaseHistoryHtmlPairedCellRows:
    """Regression coverage for a second, live-verified bug: CNR
    HBHC010536082026 (WP/26147/2026, Telangana HC) still returned
    registration_number="" after the fix above, even though its
    case-history page clearly shows a populated "Registration Number"
    row. Root cause was NOT a label-text mismatch (confirmed via
    temporary debug logging run live against the real portal response --
    the label text is exactly "Registration Number", matching
    _DETAIL_LABELS as-is). It was a row-STRUCTURE mismatch: this page
    packs the Filing Number/Date and Registration Number/Date rows as
    TWO label/value pairs inside a single <tr> (4 cells: label, value,
    label, value), and the parser's old "skip any row that isn't exactly
    2 cells" logic threw the whole row away before the label was ever
    read.

    These are the exact label/value strings the live debug dump returned
    for this CNR:
        ['Filing Number', 'WP /38647/2026', 'Filing Date', ' 05-08-2026']
        ['Registration Number', 'WP /26147/2026', 'Registration Date', '06-08-2026']
    """

    def test_registration_number_in_a_four_cell_paired_row_is_captured(self):
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr>
            <td>Filing Number</td><td>WP /38647/2026</td>
            <td>Filing Date</td><td>05-08-2026</td>
          </tr>
          <tr>
            <td>Registration Number</td><td>WP /26147/2026</td>
            <td>Registration Date</td><td>06-08-2026</td>
          </tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == "WP /26147/2026"

    def test_filing_number_in_the_same_paired_row_is_not_mistaken_for_registration_number(self):
        """Filing Number and Registration Number are genuinely different
        eCourts fields (assigned at different points in a case's
        lifecycle, and can be different values -- WP/38647/2026 filed vs
        WP/26147/2026 registered, in the real case this was verified
        against). Filing Number must never leak into registration_number
        just because it now shares a row with it."""
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr>
            <td>Filing Number</td><td>WP /38647/2026</td>
            <td>Filing Date</td><td>05-08-2026</td>
          </tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == ""

    def test_three_pairs_bundled_in_one_row_are_all_captured(self):
        """Not just 4-cell rows -- any number of label/value pairs bundled
        into a single <tr> should be walked, not just the first pair."""
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr>
            <td>Case Stage</td><td>FOR PRONOUNCEMENT OF ORDERS</td>
            <td>Registration Number</td><td>WP /26147/2026</td>
            <td>Coram</td><td>APARESH KUMAR SINGH</td>
          </tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == "WP /26147/2026"
        assert data.case_stage == "FOR PRONOUNCEMENT OF ORDERS"
        assert data.court_and_judge == "APARESH KUMAR SINGH"

    def test_ordinary_two_cell_rows_still_work_unchanged(self):
        """Regression guard for the walk-in-strides rewrite: a plain
        single label/value row (the common case) must behave exactly as
        before."""
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr><th>Case Status</th><td>CASE PENDING</td></tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.case_status == "CASE PENDING"

    def test_stray_period_in_the_middle_of_a_label_does_not_break_the_match(self):
        """Defense-in-depth per the task's ask for robustness against
        label-formatting noise generally: this isn't what broke
        HBHC010536082026 (that was the row-structure issue above), but
        the matching path should tolerate it too. A stray period splits
        what would otherwise be a valid substring match ("registration
        number" is not a substring of "registration. number") -- unless
        the label is punctuation-normalized before comparing, which is
        exactly what should happen instead of adding another guessed
        label variant."""
        from core.services.court_data.ecourts_parsing import parse_case_history_html

        html = """
        <table>
          <tr><th>Registration. Number</th><td>WP/777/2026</td></tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == "WP/777/2026"
