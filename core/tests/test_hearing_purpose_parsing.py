"""Purpose of hearing -- the per-hearing eCourts field, e.g. "NOTICE" or
"CALL WITH IAS" (District Courts) / "FOR DISMISSAL" (HC Services).

For district-court cases this is the ONLY per-hearing signal available at
all: those courts generally don't publish order PDFs the way High Courts
do, so there's no order-summary fallback covering the gap. Getting the
column mapped correctly, and confirming it is genuinely a PER-HEARING
field distinct from the case-level "Case Stage" snapshot, both matter more
here than a typical parsing edge case.

Live-verified against the real portal (read-only fetch_case_by_cnr calls,
no DB writes) for both court types before writing these fixtures:
  - District Courts (TSHC010051622024, AS/300/2024): 16 real hearing rows,
    e.g. purpose='CALL WITH IAS', purpose='NOTICE'.
  - HC Services (HBHC010003772010, WP/30265/2010): 4 real hearing rows,
    e.g. purpose='FOR DISMISSAL', purpose='FINAL HEARING', and a case_stage
    that was BLANK on that case's snapshot -- i.e. genuinely a different,
    independently-populated field, not a rename of the same value.

The HTML below is a minimal synthetic reproduction of those two shapes
(the real portal HTML isn't captured to a fixture file anywhere in this
repo), built to exercise the same generic column-header matching
(_col_index) that ecourts_parsing.py actually runs against live HTML.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User

from core.models import Case, Hearing
from core.services.court_data.ecourts_parsing import parse_case_history_html
from core.services.court_data.models import CourtCaseData, HearingRecord
from core.services.court_tracking import refresh_case_tracking


# ---------------------------------------------------------------------------
# Parser: does parse_case_history_html() actually pick "purpose" out of the
# history_table for both court types' HTML shapes?
# ---------------------------------------------------------------------------


class TestPurposeOfHearingParsing:
    def test_district_courts_history_table(self):
        html = """
        <table class="history_table">
          <tr>
            <th>Judge</th>
            <th>Business On Date</th>
            <th>Hearing Date</th>
            <th>Purpose of hearing</th>
          </tr>
          <tr>
            <td>X ADDITIONAL CHIEF JUDGE</td>
            <td>28-10-2025</td>
            <td>10-11-2025</td>
            <td>NOTICE</td>
          </tr>
          <tr>
            <td>X ADDITIONAL CHIEF JUDGE</td>
            <td>22-06-2026</td>
            <td>20-07-2026</td>
            <td>CALL WITH IAS</td>
          </tr>
        </table>
        """

        data = parse_case_history_html(html)

        assert data is not None
        assert [h.purpose for h in data.hearing_history] == ["NOTICE", "CALL WITH IAS"]
        assert [h.judge for h in data.hearing_history] == [
            "X ADDITIONAL CHIEF JUDGE",
            "X ADDITIONAL CHIEF JUDGE",
        ]

    def test_hc_services_history_table_purpose_is_distinct_from_case_stage(self):
        """The key question this feature turned on: is "Case Stage" (a
        single case-level detail-table value) the same thing as the
        per-hearing purpose column, or a genuinely different field?

        Live data said different -- this reproduces that shape: a details
        table carrying one current Case Stage, and a history_table whose
        rows carry their OWN, different, per-row purpose values."""
        html = """
        <table>
          <tr><th scope="row">Case Stage</th><td>FOR PRONOUNCEMENT OF ORDERS</td></tr>
        </table>
        <table class="history_table">
          <tr>
            <th>Hearing Date</th>
            <th>Business On Date</th>
            <th>Purpose of hearing</th>
            <th>Judge</th>
          </tr>
          <tr>
            <td>03-12-2010</td>
            <td></td>
            <td>ADMISSION (REVENUE)</td>
            <td>C.V.RAMULU</td>
          </tr>
          <tr>
            <td>29-12-2023</td>
            <td>15-12-2023</td>
            <td>FOR DISMISSAL</td>
            <td>K. SARATH</td>
          </tr>
          <tr>
            <td>02-01-2024</td>
            <td>11-12-2023</td>
            <td>FINAL HEARING</td>
            <td>K. SARATH</td>
          </tr>
        </table>
        """

        data = parse_case_history_html(html)

        assert data is not None
        assert data.case_stage == "FOR PRONOUNCEMENT OF ORDERS"
        purposes = [h.purpose for h in data.hearing_history]
        assert purposes == ["ADMISSION (REVENUE)", "FOR DISMISSAL", "FINAL HEARING"]
        # The whole point: none of the per-hearing purposes collapse to
        # the single case-level stage value.
        assert data.case_stage not in purposes


# ---------------------------------------------------------------------------
# End to end: does a fetch actually land `purpose` on the Hearing row, for
# both court types, via the real refresh_case_tracking() entry point?
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="purpose-test-advocate", password="pass-123")


def _tracked_case(owner, *, court_type, cnr):
    return Case.objects.create(
        owner=owner,
        case_number=f"CASE-{cnr}",
        title=f"Case {cnr}",
        client_name="Test Client",
        court_type=court_type,
        tracking_config={"court_type": court_type, "cnr": cnr},
        tracking_enabled=True,
    )


@pytest.mark.django_db
class TestPurposeOfHearingPopulatesOnFetch:
    @patch("core.services.court_tracking.get_provider")
    def test_district_court_fetch_populates_purpose(self, get_provider, advocate):
        case = _tracked_case(advocate, court_type="district", cnr="TSHC010051622024")
        provider = MagicMock()
        provider.fetch_case.return_value = CourtCaseData(
            cnr="TSHC010051622024",
            hearing_history=[
                HearingRecord(
                    hearing_date=date(2026, 7, 20),
                    business_date=date(2026, 6, 22),
                    purpose="CALL WITH IAS",
                    judge="X ADDITIONAL CHIEF JUDGE",
                ),
            ],
        )
        get_provider.return_value = provider

        refresh_case_tracking(case, force=True)

        hearing = Hearing.objects.get(case=case, source="ecourts")
        assert hearing.purpose == "CALL WITH IAS"

    @patch("core.services.court_tracking.get_provider")
    def test_high_court_fetch_populates_purpose(self, get_provider, advocate):
        case = _tracked_case(advocate, court_type="high_court", cnr="HBHC010003772010")
        provider = MagicMock()
        provider.fetch_case.return_value = CourtCaseData(
            cnr="HBHC010003772010",
            case_stage="",
            hearing_history=[
                HearingRecord(
                    hearing_date=date(2024, 1, 2),
                    business_date=date(2023, 12, 11),
                    purpose="FINAL HEARING",
                    judge="K. SARATH",
                ),
            ],
        )
        get_provider.return_value = provider

        refresh_case_tracking(case, force=True)

        hearing = Hearing.objects.get(case=case, source="ecourts")
        assert hearing.purpose == "FINAL HEARING"
