"""District Courts "Daily Status" (Business on Date): link + page parsing,
the worker-side fetch (immutability, caps, failure isolation) and the
read-only endpoint, including cross-tenant isolation.

The viewBusiness link arguments are parsed from a REAL captured page
(cnr_case_page/TSHC010030082026.html). The business page fixtures under
fixtures/ecourts/daily_status/ are SYNTHETIC (no live capture yet): they pin
the label-driven parser, not the portal's actual markup.
"""

from datetime import date, datetime, timezone as dt_tz
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Case, CaseBusinessEntry, Hearing
from core.services import daily_status
from core.services.court_data import BusinessLink, BusinessRecord
from core.services.court_data.ecourts_parsing import parse_business_html, parse_business_links

FIXTURES = Path(__file__).parent / "fixtures"
CASE_PAGE = FIXTURES / "causelists" / "district_ecourts" / "cnr_case_page" / "TSHC010030082026.html"
BUSINESS_DIR = FIXTURES / "ecourts" / "daily_status"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


class TestParseBusinessLinks:
    def test_real_history_page_links(self):
        links = parse_business_links(CASE_PAGE.read_text(encoding="utf-8"))
        assert links, "the captured history table carries viewBusiness links"
        dates = [link.business_date for link in links]
        assert dates == sorted(dates, reverse=True)
        assert len(dates) == len(set(dates))
        newest = links[0]
        assert newest.business_date == date(2026, 10, 9)
        assert newest.form == {
            "court_code": "2",
            "state_code": "29",
            "dist_code": "2",
            "nextdate1": "20261015",
            "case_number1": "TSHC010030082026",
            "disposal_flag": "Pending",
            "businessDate": "09-10-2026",
            "national_court_code": "TSHC01",
            "court_no": "1",
            "search_by": "cnr",
            "srno": "12",
        }

    def test_page_without_links(self):
        assert parse_business_links("<table><tr><td>nothing</td></tr></table>") == []
        assert parse_business_links("") == []


class TestParseBusinessHtml:
    @pytest.mark.parametrize("name", ["synthetic_business_table.html", "synthetic_business_labels.html"])
    def test_both_layouts(self, name):
        record = parse_business_html((BUSINESS_DIR / name).read_text(encoding="utf-8"))
        assert record is not None
        assert record.business_date == date(2026, 11, 5)
        assert record.court_name == "Principal Junior Civil Judge, Sangareddy"
        assert record.business_text == (
            "Petitioner counsel present. Respondent counsel absent. "
            "Memo filed by the petitioner counsel stay is granted. Hence call on 19.11.2026."
        )
        assert record.next_purpose == "STAY"
        assert record.next_hearing_date == date(2026, 11, 19)

    def test_party_names_are_not_carried(self):
        record = parse_business_html((BUSINESS_DIR / "synthetic_business_table.html").read_text(encoding="utf-8"))
        for value in (record.court_name, record.business_text, record.next_purpose):
            assert "versus" not in value.lower()

    @pytest.mark.parametrize(
        "html",
        ["", "   ", '{"errormsg": "Invalid Request"}', "<p>Order not uploaded</p>", "<div>Something else</div>"],
    )
    def test_empty_and_error_pages(self, html):
        assert parse_business_html(html) is None

    def test_blank_business_still_a_record_and_link_date_fallback(self):
        html = "<table><tr><td>Business</td><td>:</td><td></td></tr><tr><td>Next Purpose</td><td>:</td><td>EVIDENCE</td></tr></table>"
        record = parse_business_html(html, date(2026, 11, 1))
        assert record is not None
        assert record.business_text == ""
        assert record.next_purpose == "EVIDENCE"
        assert record.business_date == date(2026, 11, 1)
        assert record.next_hearing_date is None


# ---------------------------------------------------------------------------
# Worker-side fetch
# ---------------------------------------------------------------------------


@pytest.fixture
def alice(db):
    return User.objects.create_user(username="ds-alice", password="pw-12345")


@pytest.fixture
def bob(db):
    return User.objects.create_user(username="ds-bob", password="pw-12345")


@pytest.fixture(autouse=True)
def _fast(settings):
    settings.COURT_BUSINESS_DELAY_SECONDS = 0
    settings.COURT_BUSINESS_FETCHES_PER_SYNC = 3
    settings.COURT_BUSINESS_HISTORY_WINDOW = 10


def _district_case(owner, cnr="TSHS020000882016", business_dates=()):
    case = Case.objects.create(
        owner=owner,
        case_number="OS/88/2016",
        title="X vs Y",
        cnr_number=cnr,
        tracking_enabled=True,
        tracking_config={"court_type": "district", "cnr": cnr},
    )
    for d in business_dates:
        Hearing.objects.create(
            owner=owner,
            case=case,
            hearing_date=datetime(d.year, d.month, d.day, tzinfo=dt_tz.utc),
            hearing_type="preliminary",
            source="ecourts",
            business_date=d,
        )
    return case


def _record(d, text="Heard."):
    return BusinessRecord(
        business_date=d, court_name="Court 1", business_text=text, next_purpose="STAY",
        next_hearing_date=date(2026, 11, 19),
    )


class FakeSession:
    def __init__(self, links, outcomes):
        self.links = links
        self.outcomes = outcomes  # business_date -> BusinessRecord | None | Exception
        self.fetched: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def fetch(self, link):
        self.fetched.append(link.business_date)
        outcome = self.outcomes.get(link.business_date, _record(link.business_date))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeProvider:
    def __init__(self, session=None, error=None):
        self.session = session
        self.error = error
        self.opened = 0

    def business_session(self, config):
        self.opened += 1
        if self.error:
            raise self.error
        return self.session


D = [date(2026, 11, d) for d in (5, 4, 3, 2, 1)]


def _links(dates):
    return [BusinessLink(business_date=d, form={"businessDate": d.strftime("%d-%m-%Y")}) for d in dates]


class TestSyncCaseBusiness:
    def test_stores_newest_missing_dates_up_to_the_cap(self, alice):
        case = _district_case(alice, business_dates=D)
        session = FakeSession(_links(D), {})
        result = daily_status.sync_case_business(case, provider=FakeProvider(session))
        assert session.fetched == D[:3]
        assert result["stored"] == 3 and result["failed"] == 0
        entry = CaseBusinessEntry.objects.get(case=case, business_date=D[0])
        assert entry.owner == alice
        assert entry.next_purpose == "STAY"
        assert entry.next_hearing_date == date(2026, 11, 19)

    def test_immutable_and_no_portal_call_when_nothing_missing(self, alice):
        case = _district_case(alice, business_dates=D[:2])
        CaseBusinessEntry.objects.create(owner=alice, case=case, business_date=D[0], business_text="Original")
        session = FakeSession(_links(D[:2]), {D[0]: _record(D[0], "Changed")})
        daily_status.sync_case_business(case, provider=FakeProvider(session))
        assert session.fetched == [D[1]]  # D[0] already stored: never asked again
        assert CaseBusinessEntry.objects.get(case=case, business_date=D[0]).business_text == "Original"

        provider = FakeProvider(FakeSession(_links(D[:2]), {}))
        result = daily_status.sync_case_business(case, provider=provider)
        assert provider.opened == 0  # all stored: no session, no CAPTCHA
        assert result["wanted"] == 0
        assert CaseBusinessEntry.objects.filter(case=case).count() == 2

    def test_history_window_is_a_hard_cap(self, alice, settings):
        settings.COURT_BUSINESS_HISTORY_WINDOW = 2
        case = _district_case(alice, business_dates=D)
        for d in D[:2]:
            CaseBusinessEntry.objects.create(owner=alice, case=case, business_date=d)
        provider = FakeProvider(FakeSession(_links(D), {}))
        result = daily_status.sync_case_business(case, provider=provider)
        assert provider.opened == 0 and result["wanted"] == 0  # older dates never backfilled

    def test_one_failure_is_isolated(self, alice):
        case = _district_case(alice, business_dates=D)
        session = FakeSession(_links(D), {D[0]: RuntimeError("portal hiccup")})
        result = daily_status.sync_case_business(case, provider=FakeProvider(session))
        assert session.fetched == D[:3]
        assert result["failed"] == 1 and result["stored"] == 2
        assert not CaseBusinessEntry.objects.filter(case=case, business_date=D[0]).exists()

    def test_two_failures_in_a_row_stop(self, alice):
        case = _district_case(alice, business_dates=D)
        session = FakeSession(_links(D), {D[0]: RuntimeError("x"), D[1]: None})
        result = daily_status.sync_case_business(case, provider=FakeProvider(session))
        assert session.fetched == D[:2]
        assert result["failed"] == 2 and result["stopped_early"] is True and result["stored"] == 0

    def test_session_failure_never_raises(self, alice):
        case = _district_case(alice, business_dates=D)
        result = daily_status.sync_case_business(case, provider=FakeProvider(error=RuntimeError("captcha")))
        assert result["skipped"] == "portal" and result["failed"] == 1

    def test_unlisted_date_is_skipped_not_failed(self, alice):
        case = _district_case(alice, business_dates=D[:2])
        session = FakeSession(_links(D[1:2]), {})
        result = daily_status.sync_case_business(case, provider=FakeProvider(session))
        assert result["unlisted"] == 1 and result["stored"] == 1 and result["failed"] == 0

    def test_skips_high_court_and_untracked(self, alice):
        case = _district_case(alice, business_dates=D)
        case.tracking_config = {"court_type": "high_court", "cnr": case.cnr_number}
        case.save()
        provider = FakeProvider(FakeSession(_links(D), {}))
        assert daily_status.sync_case_business(case, provider=provider)["skipped"] == "not_district"
        assert provider.opened == 0


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestDailyStatusEndpoint:
    def test_shape_newest_first(self, alice):
        case = _district_case(alice)
        CaseBusinessEntry.objects.create(owner=alice, case=case, business_date=D[2], business_text="older")
        CaseBusinessEntry.objects.create(
            owner=alice, case=case, business_date=D[0], court_name="Court 1", business_text="newer",
            next_purpose="STAY", next_hearing_date=date(2026, 11, 19),
        )
        resp = _client(alice).get(f"/api/cases/{case.id}/daily-status/")
        assert resp.status_code == 200
        assert [row["business_date"] for row in resp.data] == ["2026-11-05", "2026-11-03"]
        assert set(resp.data[0]) == {
            "business_date", "court_name", "business_text", "next_purpose", "next_hearing_date", "fetched_at",
        }
        assert resp.data[0]["next_hearing_date"] == "2026-11-19"
        assert resp.data[1]["next_hearing_date"] is None

    def test_other_tenant_gets_404(self, alice, bob):
        case = _district_case(alice)
        CaseBusinessEntry.objects.create(owner=alice, case=case, business_date=D[0], business_text="private")
        resp = _client(bob).get(f"/api/cases/{case.id}/daily-status/")
        assert resp.status_code == 404
        assert "private" not in str(resp.data)

    def test_own_case_never_shows_foreign_rows(self, alice, bob):
        case = _district_case(alice)
        bob_case = _district_case(bob, cnr="TSHS020000992016")
        CaseBusinessEntry.objects.create(owner=bob, case=bob_case, business_date=D[0], business_text="bob's")
        resp = _client(alice).get(f"/api/cases/{case.id}/daily-status/")
        assert resp.status_code == 200 and resp.data == []

    def test_requires_auth(self, alice):
        case = _district_case(alice)
        assert APIClient().get(f"/api/cases/{case.id}/daily-status/").status_code in (401, 403)

    def test_case_payload_unchanged(self, alice):
        case = _district_case(alice)
        CaseBusinessEntry.objects.create(owner=alice, case=case, business_date=D[0], next_purpose="STAY")
        resp = _client(alice).get(f"/api/cases/{case.id}/")
        assert resp.status_code == 200
        assert "daily_status" not in resp.data and "business_entries" not in resp.data
