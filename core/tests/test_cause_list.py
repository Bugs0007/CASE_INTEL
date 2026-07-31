"""Phase B: Telangana High Court cause-list parsing and matching.

The parser is exercised against the REAL saved list in
core/tests/fixtures/causelists/ (TS High Court, court hall 1,
3 August 2026, 62 matters), not a hand-written stub -- a stub would only
prove the parser matches my own assumptions about the layout.

The two failure modes that matter most have their own tests:
  - a tracked case that is NOT in a published list must read "not listed",
  - a list the court hasn't published yet must read "not yet listed" and
    must never be confused with the above.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Case, Hearing
from core.services.cause_list import (
    CauseListNotConfiguredError,
    CauseListParseError,
    normalize_case_token,
    parse_cause_list_html,
)
from core.services.cause_list import service as cause_list_service
from core.services.cause_list.exceptions import CauseListNotPublishedError
from core.services.cause_list.telangana_hc import build_cause_list_url

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "causelists"
SAMPLE = FIXTURE_DIR / "Telangana Highcourt.html"

# The list this fixture is for.
LIST_DATE = date(2026, 8, 3)
LIST_COURT_HALL = "1"
LIST_ITEM_COUNT = 62
# Two of the 62 matters are listed by FILING number ("(Filing No.)"),
# which is a different series from a registration number and so is
# deliberately kept out of the matching index.
LIST_FILING_NUMBER_COUNT = 2
LIST_MATCHABLE_COUNT = LIST_ITEM_COUNT - LIST_FILING_NUMBER_COUNT


@pytest.fixture(scope="module")
def sample_html() -> str:
    return SAMPLE.read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def parsed(sample_html):
    return parse_cause_list_html(sample_html)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParseSampleCauseList:
    def test_header_metadata(self, parsed):
        assert parsed.court_hall == LIST_COURT_HALL
        assert parsed.list_date == LIST_DATE
        assert parsed.list_type == "DAILY LIST"

    def test_every_matter_is_parsed(self, parsed):
        assert len(parsed.items) == LIST_ITEM_COUNT

    def test_item_numbers_are_the_printed_serials(self, parsed):
        numbers = [item.item_number for item in parsed.items]
        assert numbers[0] == "1"
        assert numbers[-1] == str(LIST_ITEM_COUNT)
        # Serials are unique -- a duplicate would mean rows were double-counted.
        assert len(set(numbers)) == LIST_ITEM_COUNT

    def test_first_item_is_fully_extracted(self, parsed):
        item = parsed.items[0]
        assert item.item_number == "1"
        assert item.case_token == "WA/102/2026"
        assert (item.case_type, item.case_serial, item.case_year) == ("WA", "102", "2026")
        assert item.stage == "FOR PRONOUNCEMENT OF JUDGMENT"
        assert "PATANJALI FOODS LIMITED" in item.parties
        # The three IAs listed under the main matter.
        assert len(item.connected) == 3
        assert item.connected[0].startswith("IA 1/2026")

    def test_stage_headings_are_carried_onto_their_items(self, parsed):
        stages = {item.stage for item in parsed.items}
        assert "FOR ADMISSION (FRESH MATTERS)" in stages
        assert "FOR PRONOUNCEMENT OF JUDGMENT" in stages
        # Every item got a stage -- the per-tbody layout means a missed
        # one would silently blank the field.
        assert all(item.stage for item in parsed.items)

    def test_index_is_keyed_by_normalized_case(self, parsed):
        index = parsed.index_by_case()
        assert ("WA", "102", "2026") in index
        assert index[("WA", "102", "2026")].item_number == "1"
        assert len(index) == LIST_MATCHABLE_COUNT

    def test_every_case_token_in_the_list_is_parseable(self, parsed):
        """A token this parser can't read is a case that would silently
        read 'not listed' for its advocate."""
        unreadable = [i.case_token for i in parsed.items if i.normalized_key is None]
        assert unreadable == []

    def test_parenthesised_case_types_are_handled(self, parsed):
        """This court prints PIL writs as 'WP(PIL)/58/2023'."""
        index = parsed.index_by_case()
        assert ("WP(PIL)", "58", "2023") in index
        assert index[("WP(PIL)", "58", "2023")].item_number == "52"

    def test_filing_number_entries_are_parsed_but_not_matchable(self, parsed):
        """A filing number and a registration number are independent
        series that collide, so matching on one would eventually stamp
        another matter's item number onto a real hearing."""
        filing = [i for i in parsed.items if i.is_filing_number]
        assert len(filing) == LIST_FILING_NUMBER_COUNT
        assert {i.item_number for i in filing} == {"18", "19"}

        index = parsed.index_by_case()
        # WA/36270/2026 appears ONLY as a filing number, so it must not
        # be matchable.
        assert ("WA", "36270", "2026") not in index

    def test_interlocutory_entries_are_not_matchable_items(self, parsed):
        """An IA number is not the main case's identity -- matching one
        would stamp the wrong item number onto a case."""
        index = parsed.index_by_case()
        assert ("IA", "1", "2026") not in index


class TestParserRejectsWrongDocuments:
    def test_empty_document(self):
        with pytest.raises(CauseListParseError):
            parse_cause_list_html("")

    def test_unrelated_html(self):
        with pytest.raises(CauseListParseError):
            parse_cause_list_html("<html><body><h1>Portal under maintenance</h1></body></html>")

    def test_right_table_but_no_items(self):
        """An empty table is treated as a layout change, not as 'nobody
        is listed today' -- the latter would silently mark every tracked
        case 'not listed'."""
        with pytest.raises(CauseListParseError):
            parse_cause_list_html(
                "<table id='dataTable'><thead>COURT NO. 1</thead><tbody></tbody></table>"
            )


class TestNormalizeCaseToken:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("WA/102/2026", ("WA", "102", "2026")),
            ("W.A./102/2026", ("WA", "102", "2026")),
            ("wa/102/2026", ("WA", "102", "2026")),
            ("WA 102 of 2026", ("WA", "102", "2026")),
            ("WA-102-2026", ("WA", "102", "2026")),
            ("WP/0024113/2026", ("WP", "24113", "2026")),
            ("CC/3550/2026", ("CC", "3550", "2026")),
            ("WP(PIL)/58/2023", ("WP(PIL)", "58", "2023")),
        ],
    )
    def test_equivalent_spellings_normalize_together(self, raw, expected):
        assert normalize_case_token(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            None,
            "TSHC010051622024",          # a CNR, not a case number
            "2^2/300/2024",              # a district portal case-type code
            "not a case",
        ],
    )
    def test_unparseable_tokens_return_none(self, raw):
        assert normalize_case_token(raw) is None


# ---------------------------------------------------------------------------
# Matching against tracked hearings
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="cause-list-advocate", password="pass-123")


def _hc_case(owner, case_number, **kwargs):
    defaults = {
        "owner": owner,
        "case_number": case_number,
        "title": case_number,
        "client_name": "Client",
        "court_type": "high_court",
        "tracking_enabled": True,
    }
    defaults.update(kwargs)
    return Case.objects.create(**defaults)


def _hearing_on(owner, case, day=LIST_DATE, status="scheduled"):
    return Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=timezone.make_aware(datetime.combine(day, datetime.min.time())),
        hearing_type="other",
        status=status,
        source="ecourts",
    )


@pytest.mark.django_db
class TestApplyCauseList:
    def test_a_listed_case_gets_its_item_number_and_court_hall(self, advocate, sample_html):
        case = _hc_case(advocate, "WP/24113/2026")
        hearing = _hearing_on(advocate, case)

        result = cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        hearing.refresh_from_db()
        assert result["status"] == "applied"
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "6"
        assert hearing.cause_list_court_hall == LIST_COURT_HALL
        assert hearing.cause_list_stage == "FOR ADMISSION (FRESH MATTERS)"
        assert hearing.cause_list_checked_at is not None
        assert hearing.cause_list_source == "telangana_hc"

    def test_a_case_that_is_not_listed_is_recorded_as_not_listed(
        self, advocate, sample_html
    ):
        """The required negative case: the list IS published, and this
        matter simply isn't in it."""
        case = _hc_case(advocate, "WP/99999/2026")
        hearing = _hearing_on(advocate, case)

        result = cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_LISTED
        assert hearing.cause_list_item_number == ""
        assert hearing.cause_list_court_hall == ""
        assert hearing.cause_list_checked_at is not None
        assert result["not_listed"] == 1
        assert result["listed"] == 0

    def test_listed_and_not_listed_in_one_run(self, advocate, sample_html):
        listed_case = _hc_case(advocate, "WA/789/2026")
        missing_case = _hc_case(advocate, "WP/88888/2026")
        listed_hearing = _hearing_on(advocate, listed_case)
        missing_hearing = _hearing_on(advocate, missing_case)

        result = cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        listed_hearing.refresh_from_db()
        missing_hearing.refresh_from_db()
        assert listed_hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert listed_hearing.cause_list_item_number == "3"
        assert missing_hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_LISTED
        assert result["listed"] == 1
        assert result["not_listed"] == 1

    def test_case_number_spelling_differences_still_match(self, advocate, sample_html):
        """The list prints 'WA/789/2026'; the tracked case was created
        with punctuation from a different portal response."""
        case = _hc_case(advocate, "W.A. 789 of 2026")
        hearing = _hearing_on(advocate, case)

        cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "3"

    def test_case_matched_via_tracking_config_when_case_number_is_a_cnr(
        self, advocate, sample_html
    ):
        """advocate_import falls back to the CNR for case_number when the
        portal gives no case number -- the identity then has to come from
        tracking_config instead."""
        case = _hc_case(
            advocate,
            "TSHC010051622026",
            tracking_config={
                "court_type": "high_court",
                "case_type": "WA",
                "case_number": "790",
                "year": "2026",
            },
        )
        hearing = _hearing_on(advocate, case)

        cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "4"

    def test_case_with_no_parseable_number_is_unmatchable_not_not_listed(
        self, advocate, sample_html, caplog
    ):
        """Absence proves nothing when there was no number to look for,
        so the row must not be stamped 'not listed'."""
        case = _hc_case(advocate, "TSHC010051622024", tracking_config={"cnr": "TSHC010051622024"})
        hearing = _hearing_on(advocate, case)

        with caplog.at_level(logging.WARNING, logger="core.services.cause_list.service"):
            result = cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED
        assert result["unmatchable"] == 1
        assert result["not_listed"] == 0

    def test_unmatched_listed_matters_are_counted(self, advocate, sample_html):
        case = _hc_case(advocate, "WA/102/2026")
        _hearing_on(advocate, case)

        result = cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        assert result["total_items"] == LIST_MATCHABLE_COUNT
        # Every matchable matter but ours belongs to no tracked case.
        assert result["unmatched_items"] == LIST_MATCHABLE_COUNT - 1

    def test_district_court_cases_are_not_checked_against_the_high_court_list(
        self, advocate, sample_html
    ):
        """A district case can never appear here; checking it would
        produce a false 'not listed'."""
        case = _hc_case(advocate, "WA/102/2026", court_type="district")
        hearing = _hearing_on(advocate, case)

        result = cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        hearing.refresh_from_db()
        assert result["status"] == "no_hearings"
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED

    def test_untracked_and_cancelled_hearings_are_skipped(self, advocate, sample_html):
        untracked = _hc_case(advocate, "WA/102/2026", tracking_enabled=False)
        cancelled_case = _hc_case(advocate, "WA/789/2026")
        untracked_hearing = _hearing_on(advocate, untracked)
        cancelled_hearing = _hearing_on(advocate, cancelled_case, status="cancelled")

        result = cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        untracked_hearing.refresh_from_db()
        cancelled_hearing.refresh_from_db()
        assert result["status"] == "no_hearings"
        assert untracked_hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED
        assert cancelled_hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED

    def test_hearings_on_other_dates_are_untouched(self, advocate, sample_html):
        case = _hc_case(advocate, "WA/102/2026")
        other_day = _hearing_on(advocate, case, day=LIST_DATE + timedelta(days=1))

        cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        other_day.refresh_from_db()
        assert other_day.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED

    def test_a_list_for_the_wrong_date_is_not_applied(self, advocate, sample_html):
        """If the portal serves a different day's list, applying it would
        stamp wrong item numbers onto real hearings."""
        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case, day=LIST_DATE + timedelta(days=1))

        result = cause_list_service.check_cause_list_for_date(
            LIST_DATE + timedelta(days=1), html=sample_html
        )

        hearing.refresh_from_db()
        assert result["status"] == "date_mismatch"
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED

    def test_a_parse_failure_leaves_hearings_untouched(self, advocate):
        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)

        result = cause_list_service.check_cause_list_for_date(
            LIST_DATE, html="<html>portal down</html>"
        )

        hearing.refresh_from_db()
        assert result["status"] == "parse_error"
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED


# ---------------------------------------------------------------------------
# Not-yet-published path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotYetPublished:
    def test_hearings_are_marked_not_yet_listed(self, advocate, monkeypatch):
        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)

        def _not_published(target_date, **kwargs):
            raise CauseListNotPublishedError("No cause list published yet (HTTP 404).")

        monkeypatch.setattr(cause_list_service, "fetch_cause_list", _not_published)

        result = cause_list_service.check_cause_list_for_date(LIST_DATE)

        hearing.refresh_from_db()
        assert result["status"] == "not_published"
        assert result["marked"] == 1
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_PUBLISHED
        assert hearing.cause_list_item_number == ""
        assert hearing.cause_list_checked_at is not None

    def test_not_published_is_distinct_from_not_listed(self, advocate, monkeypatch):
        """The whole point of the two states: before publication the
        advocate must not be told their matter isn't listed."""
        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)

        monkeypatch.setattr(
            cause_list_service,
            "fetch_cause_list",
            lambda *a, **k: (_ for _ in ()).throw(CauseListNotPublishedError("404")),
        )
        cause_list_service.check_cause_list_for_date(LIST_DATE)

        hearing.refresh_from_db()
        assert hearing.cause_list_status != Hearing.CAUSE_LIST_NOT_LISTED
        assert hearing.get_cause_list_status_display() == "Not yet listed"

    def test_an_already_listed_hearing_is_not_downgraded(self, advocate, monkeypatch):
        """Once an item number is known, a later failed fetch (the list
        being pulled, a network blip) must not erase it."""
        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)
        hearing.cause_list_status = Hearing.CAUSE_LIST_LISTED
        hearing.cause_list_item_number = "1"
        hearing.cause_list_court_hall = "1"
        hearing.save()

        monkeypatch.setattr(
            cause_list_service,
            "fetch_cause_list",
            lambda *a, **k: (_ for _ in ()).throw(CauseListNotPublishedError("404")),
        )
        cause_list_service.check_cause_list_for_date(LIST_DATE)

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "1"

    def test_network_failure_is_treated_as_not_published(self, advocate, monkeypatch, settings):
        """A portal that can't be reached is operationally the same as
        one that hasn't published -- try again next run, don't claim the
        case isn't listed."""
        import requests

        settings.TELANGANA_HC_CAUSE_LIST_URL = "https://example.invalid/list?d={date}"
        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)

        def _boom(*args, **kwargs):
            raise requests.RequestException("connection refused")

        monkeypatch.setattr(requests, "get", _boom)

        result = cause_list_service.check_cause_list_for_date(LIST_DATE)

        hearing.refresh_from_db()
        assert result["status"] == "not_published"
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_PUBLISHED


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestCauseListUrl:
    def test_url_template_placeholders(self, settings):
        settings.TELANGANA_HC_CAUSE_LIST_URL = (
            "https://example.test/cl?d={dd}-{mm}-{yyyy}&iso={date}"
        )
        assert build_cause_list_url(date(2026, 8, 3)) == (
            "https://example.test/cl?d=03-08-2026&iso=2026-08-03"
        )

    def test_missing_url_raises_rather_than_guessing(self, settings):
        settings.TELANGANA_HC_CAUSE_LIST_URL = ""
        with pytest.raises(CauseListNotConfiguredError) as exc:
            build_cause_list_url(date(2026, 8, 3))
        assert "TELANGANA_HC_CAUSE_LIST_URL" in str(exc.value)

    @pytest.mark.django_db
    def test_unconfigured_url_does_not_mark_hearings_not_published(
        self, advocate, settings
    ):
        """A missing setting is an operator problem -- misreporting it as
        'the court hasn't published' would hide it indefinitely."""
        settings.TELANGANA_HC_CAUSE_LIST_URL = ""
        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)

        with pytest.raises(CauseListNotConfiguredError):
            cause_list_service.check_cause_list_for_date(LIST_DATE)

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED


# ---------------------------------------------------------------------------
# Management command + API surface
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFetchCauseListsCommand:
    def test_runs_against_a_saved_file(self, advocate):
        from io import StringIO

        from django.core.management import call_command

        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)

        out = StringIO()
        call_command(
            "fetch_cause_lists",
            "--date",
            LIST_DATE.isoformat(),
            "--html-file",
            str(SAMPLE),
            stdout=out,
        )

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "1"
        assert "1 listed" in out.getvalue()

    def test_unconfigured_url_fails_the_run_loudly(self, advocate, settings):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        settings.TELANGANA_HC_CAUSE_LIST_URL = ""
        case = _hc_case(advocate, "WA/102/2026")
        _hearing_on(advocate, case)

        with pytest.raises(CommandError) as exc:
            call_command("fetch_cause_lists", "--date", LIST_DATE.isoformat())
        assert "TELANGANA_HC_CAUSE_LIST_URL" in str(exc.value)


@pytest.mark.django_db
class TestHearingSerializerCauseListFields:
    def test_fields_are_exposed_and_read_only(self, advocate, sample_html):
        from rest_framework.test import APIClient

        case = _hc_case(advocate, "WA/102/2026")
        hearing = _hearing_on(advocate, case)
        cause_list_service.check_cause_list_for_date(LIST_DATE, html=sample_html)

        client = APIClient()
        client.force_authenticate(user=advocate)

        response = client.get(f"/api/hearings/{hearing.id}/")
        assert response.data["cause_list_status"] == "listed"
        assert response.data["cause_list_status_display"] == "Listed"
        assert response.data["cause_list_item_number"] == "1"
        assert response.data["cause_list_court_hall"] == "1"

        # Written only by the fetch job, never by a client.
        client.patch(
            f"/api/hearings/{hearing.id}/",
            {"cause_list_item_number": "999"},
            format="json",
        )
        hearing.refresh_from_db()
        assert hearing.cause_list_item_number == "1"
