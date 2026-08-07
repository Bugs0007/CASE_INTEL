"""Telangana High Court cause list, tested against REAL artifacts.

Every fixture under core/tests/fixtures/causelists/live_2026-08-03/ was
captured from a live CAPTCHA-gated run on 3 Aug 2026:

    00_meta_table.html    the showCauseList response (58 rows)
    00_row_inventory.tsv  serial / list type / bench for all 58
    *.pdf                 one real cause list per distinct list type

Nothing here is synthesised from a guess about the portal's shape. The
earlier version of this suite tested an HTML parser against a
hand-assembled sample that turned out not to come from this portal at
all, which is exactly the failure these fixtures exist to prevent.
"""

import datetime
import pathlib
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from core.models import Case, Hearing
from core.services.cause_list import (
    CauseListDay,
    CauseListNotPublishedError,
    CauseListParseError,
    build_pdf_url,
    normalize_case_token,
    parse_cause_list_pdf,
    parse_meta_table,
    strip_pdf_bom,
)
from core.services.cause_list.service import (
    apply_cause_list,
    candidate_keys_for_case,
    check_cause_list_for_date,
    mark_not_published,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "causelists" / "live_2026-08-03"
LIST_DATE = datetime.date(2026, 8, 3)

# The eight distinct cause-list types the court actually published that
# day, with the file that carries each.
PDF_FIXTURES = {
    "ADJOURNED MOTION LIST": "ADJOURNED_MOTION_LIST__B_Vijaysen_Reddy.pdf",
    "BAIL PETITIONS": "BAIL_PETITIONS__N_TUKARAMJI.pdf",
    "DAILY LIST-1": "DAILY_LIST_1__B_Vijaysen_Reddy.pdf",
    "DAILY LIST -2": "DAILY_LIST__2__TANGIRALA_MADHAVI_DEVI.pdf",
    "DAILY LIST": "DAILY_LIST__APARESH_KUMAR_SINGH__G_M__MOHIUDDIN.pdf",
    "MOTION LIST-1": "MOTION_LIST_1__K__SARATH.pdf",
    "MOTION LIST": "MOTION_LIST__B_Vijaysen_Reddy.pdf",
    "SPECIALLY MENTIONED LIST": "SPECIALLY_MENTIONED_LIST__B_Vijaysen_Reddy.pdf",
}


def read_pdf(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def meta_html() -> str:
    return (FIXTURES / "00_meta_table.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def all_documents():
    """Every fixture PDF parsed once -- pdfminer is slow."""
    return [
        parse_cause_list_pdf(read_pdf(name), list_type=list_type)
        for list_type, name in PDF_FIXTURES.items()
    ]


@pytest.fixture(scope="module")
def day(all_documents):
    return CauseListDay(list_date=LIST_DATE, documents=all_documents)


# ---------------------------------------------------------------------------
# The two portal/library bugs
# ---------------------------------------------------------------------------


class TestPortalQuirks:
    def test_strip_pdf_bom_exposes_the_header(self):
        assert strip_pdf_bom(b"\xef\xbb\xbf%PDF-1.4\nrest").startswith(b"%PDF-1.4")

    def test_strip_pdf_bom_leaves_clean_pdfs_alone(self):
        clean = b"%PDF-1.4\nbody"
        assert strip_pdf_bom(clean) == clean

    def test_strip_pdf_bom_handles_empty_input(self):
        assert strip_pdf_bom(b"") == b""

    def test_strip_pdf_bom_leaves_non_pdf_untouched(self):
        """No %PDF anywhere -> return as-is, so the caller's parser
        produces the real error."""
        assert strip_pdf_bom(b"<html>nope</html>") == b"<html>nope</html>"

    def test_bom_prefixed_pdf_still_parses(self):
        """End-to-end proof the BOM fix matters: re-attach the portal's
        prefix and the document must still parse."""
        raw = read_pdf(PDF_FIXTURES["DAILY LIST"])
        doc = parse_cause_list_pdf(b"\xef\xbb\xbf" + raw)
        assert doc.items

    def test_pdf_url_does_not_double_up_the_path(self):
        """bharat_courts builds '<base>/cases_qry/cases/display_...' which
        is a hard 404. The href already contains its own directory."""
        url = build_pdf_url("cases/display_causelist_pdf.php?filename=abc")
        assert url.endswith("/hcservices/cases/display_causelist_pdf.php?filename=abc")
        assert "cases_qry/cases" not in url

    def test_pdf_url_passes_absolute_urls_through(self):
        absolute = "https://example.test/x.pdf"
        assert build_pdf_url(absolute) == absolute

    def test_pdf_url_of_empty_href_is_empty(self):
        assert build_pdf_url("") == ""

    def test_real_meta_table_hrefs_build_the_verified_url(self):
        entries = parse_meta_table(meta_html())
        url = entries[0].pdf_url
        assert url.startswith("https://hcservices.ecourts.gov.in/hcservices/cases/")
        assert "cases_qry" not in url


# ---------------------------------------------------------------------------
# Meta table
# ---------------------------------------------------------------------------


class TestMetaTable:
    def test_parses_all_58_rows(self):
        assert len(parse_meta_table(meta_html())) == 58

    def test_matches_the_captured_row_inventory(self):
        """Cross-check against the TSV captured in the same live run."""
        rows = (FIXTURES / "00_row_inventory.tsv").read_text(
            encoding="utf-8"
        ).splitlines()[1:]
        expected = [line.split("\t") for line in rows if line.strip()]
        entries = parse_meta_table(meta_html())

        assert len(entries) == len(expected)
        for entry, (serial, list_type, bench) in zip(entries, expected):
            assert entry.serial == serial
            assert entry.list_type == list_type
            assert entry.bench == bench

    def test_finds_all_eight_list_types(self):
        types = {e.list_type for e in parse_meta_table(meta_html())}
        assert types == set(PDF_FIXTURES)

    def test_type_distribution_matches_the_live_run(self):
        entries = parse_meta_table(meta_html())
        counts = {t: sum(1 for e in entries if e.list_type == t) for t in PDF_FIXTURES}
        assert counts == {
            "DAILY LIST": 28,
            "MOTION LIST": 10,
            "ADJOURNED MOTION LIST": 7,
            "DAILY LIST-1": 7,
            "BAIL PETITIONS": 2,
            "DAILY LIST -2": 2,
            "MOTION LIST-1": 1,
            "SPECIALLY MENTIONED LIST": 1,
        }

    def test_benches_are_judge_names(self):
        """Telangana has ONE bench ('1', Principal Bench at Hyderabad);
        these values are judge combinations, not seats."""
        benches = {e.bench for e in parse_meta_table(meta_html())}
        assert "APARESH KUMAR SINGH, G.M. MOHIUDDIN" in benches
        assert len(benches) > 8

    def test_empty_response_is_a_parse_error(self):
        with pytest.raises(CauseListParseError):
            parse_meta_table("")

    def test_short_tableless_response_means_nothing_published(self):
        """The caller turns [] into CauseListNotPublishedError, which is
        very different from a parse failure."""
        assert parse_meta_table("<html><body>No record found</body></html>") == []

    def test_long_tableless_response_is_a_parse_error(self):
        """A big response with no table is a layout change, not an empty
        day -- failing loudly beats reporting every case 'not listed'."""
        with pytest.raises(CauseListParseError):
            parse_meta_table("<html><body>" + ("x" * 3000) + "</body></html>")


# ---------------------------------------------------------------------------
# PDF parsing -- every list type
# ---------------------------------------------------------------------------


class TestPdfParsing:
    @pytest.mark.parametrize("list_type,filename", sorted(PDF_FIXTURES.items()))
    def test_every_list_type_parses(self, list_type, filename):
        """All eight, not just DAILY LIST. Three of these silently parsed
        as EMPTY until column detection used row evidence."""
        doc = parse_cause_list_pdf(read_pdf(filename), list_type=list_type)
        assert doc.items, f"{list_type} produced no items"
        assert doc.court_hall, f"{list_type} has no court hall"
        assert doc.list_date == LIST_DATE

    @pytest.mark.parametrize("list_type,filename", sorted(PDF_FIXTURES.items()))
    def test_every_item_has_a_number_and_a_case(self, list_type, filename):
        doc = parse_cause_list_pdf(read_pdf(filename), list_type=list_type)
        for item in doc.items:
            assert item.item_number
            assert item.case_token
            # A long token means a whole paragraph leaked into the case
            # column -- i.e. the column detection drifted.
            assert len(item.case_token) < 60, item.case_token

    def test_court_halls_differ_between_documents(self, all_documents):
        """The hall is a property of the document, not the day -- which is
        why it is stored per item."""
        halls = {d.court_hall for d in all_documents}
        assert halls == {"1", "4", "6", "10", "13"}

    def test_daily_list_item_one(self):
        doc = parse_cause_list_pdf(read_pdf(PDF_FIXTURES["DAILY LIST"]))
        first = doc.items[0]
        assert first.item_number == "1"
        assert first.case_token == "WA/102/2026"
        assert first.court_hall == "1"
        assert first.stage == "FOR PRONOUNCEMENT OF JUDGMENT"

    def test_item_two_is_paired_with_its_own_case(self):
        """The regression that motivated coordinate parsing: pdfminer's
        plain text order puts CC/3550/2026 several lines from item 2."""
        doc = parse_cause_list_pdf(read_pdf(PDF_FIXTURES["DAILY LIST"]))
        item = next(i for i in doc.items if i.item_number == "2")
        assert item.case_token == "CC/3550/2026"

    def test_connected_ia_entries_are_kept_but_are_not_the_case(self):
        doc = parse_cause_list_pdf(read_pdf(PDF_FIXTURES["DAILY LIST"]))
        first = doc.items[0]
        assert first.case_token == "WA/102/2026"
        assert any("IA 1/2026" in c for c in first.connected)

    def test_tagged_wt_items_are_captured(self):
        """'wt4 WP/21946/2024' -- a matter tagged to item 4, printed in
        the item column. Dropping these loses real listings: this
        document's plain numbers jump 3 -> 7."""
        doc = parse_cause_list_pdf(read_pdf(PDF_FIXTURES["ADJOURNED MOTION LIST"]))
        tagged = [i for i in doc.items if i.item_number.lower().startswith("wt")]
        assert tagged
        wt4 = next(i for i in tagged if i.item_number == "wt4")
        assert wt4.case_token == "WP/21946/2024"

    def test_stage_headings_are_carried_down_the_list(self):
        doc = parse_cause_list_pdf(read_pdf(PDF_FIXTURES["BAIL PETITIONS"]))
        stages = {i.stage for i in doc.items}
        assert "ANTICIPATORY BAIL PETITIONS" in stages

    def test_page_headers_are_not_mistaken_for_cases(self, all_documents):
        """Continuation pages repeat 'MOTION LIST CAUSELIST COURT NO 4...'
        inside the case column."""
        for doc in all_documents:
            for item in doc.items:
                assert "CAUSELIST" not in item.case_token.upper()
                assert "HYDERABAD" not in item.case_token.upper()

    def test_multi_page_documents_keep_going_past_page_one(self):
        doc = parse_cause_list_pdf(read_pdf(PDF_FIXTURES["DAILY LIST"]))
        assert len(doc.items) > 40

    def test_meta_table_list_type_wins_over_the_pdf_header(self):
        """The PDFs spell these inconsistently ('DAILY LIST-1' vs
        'DAILY LIST -2'), so the meta table is authoritative."""
        doc = parse_cause_list_pdf(
            read_pdf(PDF_FIXTURES["DAILY LIST -2"]), list_type="DAILY LIST -2"
        )
        assert doc.list_type == "DAILY LIST -2"

    def test_bench_is_recorded_from_the_meta_table(self):
        doc = parse_cause_list_pdf(
            read_pdf(PDF_FIXTURES["DAILY LIST"]),
            bench="APARESH KUMAR SINGH, G.M. MOHIUDDIN",
        )
        assert doc.bench == "APARESH KUMAR SINGH, G.M. MOHIUDDIN"
        assert all(i.bench == "APARESH KUMAR SINGH, G.M. MOHIUDDIN" for i in doc.items)

    def test_non_pdf_input_raises_rather_than_returning_empty(self):
        with pytest.raises(CauseListParseError):
            parse_cause_list_pdf(b"<html><body>not a pdf</body></html>")

    def test_empty_input_raises(self):
        with pytest.raises(CauseListParseError):
            parse_cause_list_pdf(b"")


# ---------------------------------------------------------------------------
# The day-level index
# ---------------------------------------------------------------------------


class TestCauseListDay:
    def test_day_aggregates_every_document(self, day):
        assert len(day.documents) == 8
        assert len(day.items) > 200

    def test_index_spans_documents(self, day):
        """A DAILY LIST matter (hall 1) and a BAIL PETITIONS matter
        (hall 13) must both be findable from one index."""
        index = day.index_by_case()
        assert index[("WA", "102", "2026")].court_hall == "1"
        assert index[("CRLP", "12410", "2026")].court_hall == "13"

    def test_index_keeps_the_item_number_with_the_right_hall(self, day):
        item = day.index_by_case()[("WA", "102", "2026")]
        assert item.item_number == "1"
        assert item.list_type == "DAILY LIST"

    def test_filing_numbers_are_excluded_from_the_index(self, day):
        """Filing and registration numbers are independent series that
        collide; indexing both would eventually stamp another matter's
        item number onto a real hearing."""
        index = day.index_by_case()
        assert all(not item.is_filing_number for item in index.values())


class TestNormalizeCaseToken:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("WA/102/2026", ("WA", "102", "2026")),
            ("W.A./102/2026", ("WA", "102", "2026")),
            ("WA/0102/2026", ("WA", "102", "2026")),
            ("WA 102 of 2026", ("WA", "102", "2026")),
            ("WP(PIL)/58/2023", ("WP(PIL)", "58", "2023")),
            ("CRLP/12410/2026", ("CRLP", "12410", "2026")),
        ],
    )
    def test_equivalent_spellings_normalize_together(self, raw, expected):
        assert normalize_case_token(raw) == expected

    @pytest.mark.parametrize("raw", ["", None, "TSHC010051622026", "not a case", "2^2"])
    def test_unparseable_tokens_return_none(self, raw):
        assert normalize_case_token(raw) is None


# ---------------------------------------------------------------------------
# Matching against tracked hearings
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="cause-list-advocate", password="pass-123")


def make_hearing(owner, case_number, *, court_type="high_court"):
    case = Case.objects.create(
        owner=owner,
        case_number=case_number,
        title=case_number,
        client_name="",
        court_type=court_type,
        tracking_enabled=True,
        tracking_config={"court_type": court_type, "cnr": "TSHC010051622026"},
    )
    return Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=timezone.make_aware(datetime.datetime(2026, 8, 3, 0, 0)),
        hearing_type="other",
        source="ecourts",
        status="scheduled",
    )


@pytest.mark.django_db
class TestApplyCauseList:
    def test_a_listed_case_gets_its_item_number_and_hall(self, advocate, day):
        hearing = make_hearing(advocate, "WA/102/2026")
        result = apply_cause_list(day, [hearing])

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "1"
        assert hearing.cause_list_court_hall == "1"
        assert result["listed"] == 1

    def test_a_case_in_a_non_daily_list_is_found_too(self, advocate, day):
        """Parsing only DAILY LIST would miss 30 of the 58 documents."""
        hearing = make_hearing(advocate, "CRLP/12410/2026")
        apply_cause_list(day, [hearing])

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_court_hall == "13"

    def test_a_case_that_is_NOT_listed_is_recorded_as_such(self, advocate, day):
        hearing = make_hearing(advocate, "WP/99999/2099")
        result = apply_cause_list(day, [hearing])

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_LISTED
        assert hearing.cause_list_item_number == ""
        assert result["not_listed"] == 1

    def test_a_case_with_no_parseable_number_is_unmatchable_not_absent(
        self, advocate, day
    ):
        """Absence proves nothing when there was no number to look for."""
        hearing = make_hearing(advocate, "TSHC010051622026")
        result = apply_cause_list(day, [hearing])

        hearing.refresh_from_db()
        assert result["unmatchable"] == 1
        assert hearing.cause_list_status != Hearing.CAUSE_LIST_NOT_LISTED

    def test_alternate_spelling_still_matches(self, advocate, day):
        hearing = make_hearing(advocate, "W.A./0102/2026")
        apply_cause_list(day, [hearing])

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "1"

    def test_a_tagged_wt_item_matches_with_its_wt_number(self, advocate, day):
        hearing = make_hearing(advocate, "WP/21946/2024")
        apply_cause_list(day, [hearing])

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "wt4"

    def test_result_reports_documents_and_halls(self, advocate, day):
        result = apply_cause_list(day, [make_hearing(advocate, "WA/102/2026")])
        assert result["documents"] == 8
        assert result["court_halls"] == ["1", "10", "13", "4", "6"]

    def test_candidate_keys_reads_more_than_case_number(self, advocate):
        hearing = make_hearing(advocate, "TSHC010051622026")
        hearing.case.tracking_config = {
            "court_type": "high_court",
            "case_type": "WA",
            "case_number": "102",
            "year": "2026",
        }
        hearing.case.save()
        assert ("WA", "102", "2026") in candidate_keys_for_case(hearing.case)


# ---------------------------------------------------------------------------
# Not-yet-published, and the other non-applying paths
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestNotPublished:
    def test_marks_hearings_not_yet_listed(self, advocate):
        hearing = make_hearing(advocate, "WA/102/2026")
        assert mark_not_published([hearing]) == 1

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_PUBLISHED

    def test_an_already_listed_hearing_is_never_downgraded(self, advocate):
        """Once an item number is known, a later failed fetch must not
        erase it."""
        hearing = make_hearing(advocate, "WA/102/2026")
        hearing.cause_list_status = Hearing.CAUSE_LIST_LISTED
        hearing.cause_list_item_number = "1"
        hearing.save()

        assert mark_not_published([hearing]) == 0
        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "1"

    @patch("core.services.cause_list.service.fetch_cause_list_day")
    def test_unpublished_date_records_not_yet_listed(self, fetch, advocate):
        fetch.side_effect = CauseListNotPublishedError("nothing for that date")
        hearing = make_hearing(advocate, "WA/102/2026")

        result = check_cause_list_for_date(LIST_DATE)

        assert result["status"] == "not_published"
        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_PUBLISHED

    @patch("core.services.cause_list.service.fetch_cause_list_day")
    def test_parse_failure_leaves_hearings_untouched(self, fetch, advocate):
        """A parser break must NOT read as 'your case isn't listed'."""
        fetch.side_effect = CauseListParseError("layout changed")
        hearing = make_hearing(advocate, "WA/102/2026")

        result = check_cause_list_for_date(LIST_DATE)

        assert result["status"] == "parse_error"
        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED

    def test_no_tracked_hearings_is_a_no_op(self, advocate, db):
        result = check_cause_list_for_date(datetime.date(2026, 8, 4))
        assert result["status"] == "no_hearings"

    def test_district_cases_are_not_checked_against_the_high_court(self, advocate):
        """A district case would always read 'not listed' here."""
        make_hearing(advocate, "WA/102/2026", court_type="district")
        result = check_cause_list_for_date(LIST_DATE)
        assert result["status"] == "no_hearings"

    def test_wrong_date_document_is_not_applied(self, advocate, day):
        """The portal serving another day's list must not stamp wrong item
        numbers onto real hearings."""
        make_hearing(advocate, "WA/102/2026")
        assert check_cause_list_for_date(LIST_DATE, cause_list_day=day)["status"] == "applied"

        other = CauseListDay(
            list_date=datetime.date(2026, 8, 10), documents=day.documents
        )
        result = check_cause_list_for_date(LIST_DATE, cause_list_day=other)
        assert result["status"] == "date_mismatch"

    def test_end_to_end_against_the_real_fixtures(self, advocate, day):
        """One listed case, one absent case, one unmatchable -- all
        resolved from the same real day's documents."""
        listed = make_hearing(advocate, "WA/102/2026")
        absent = make_hearing(advocate, "WP/99999/2099")
        unmatchable = make_hearing(advocate, "TSHC010051622026")

        result = check_cause_list_for_date(LIST_DATE, cause_list_day=day)

        assert result["status"] == "applied"
        assert result["listed"] == 1
        assert result["not_listed"] == 1
        assert result["unmatchable"] == 1

        listed.refresh_from_db()
        absent.refresh_from_db()
        unmatchable.refresh_from_db()
        assert listed.cause_list_item_number == "1"
        assert listed.cause_list_court_hall == "1"
        assert absent.cause_list_status == Hearing.CAUSE_LIST_NOT_LISTED
        assert unmatchable.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED
