"""diagnose_orders: the verdict logic, the pacing and the "no page text" rule.

None of this touches the database or the network: `diagnose_page` and
`run_diagnosis` are pure, and the page is the one real captured District
Courts CNR page (core/tests/fixtures/causelists/district_ecourts/cnr_case_page)
plus variants made by editing it.
"""

from pathlib import Path
from types import SimpleNamespace

from core.management.commands.diagnose_orders import (
    ERROR,
    MATCH,
    MIN_SPACING_SECONDS,
    PARSER_MISS,
    PORTAL_EMPTY,
    diagnose_page,
    format_table,
    run_diagnosis,
)

PAGE = (
    Path(__file__).parent
    / "fixtures/causelists/district_ecourts/cnr_case_page/TSHC010030082026.html"
)
CNR = "TSHC010030082026"
PARTY = "PEOPLE MEDIA FACTORY"  # a party name on the real page: must never be printed


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def case(id_=1, court_type="district", cnr=CNR):
    return SimpleNamespace(id=id_, court_type=court_type, cnr_number=cnr, tracking_config={"cnr": cnr})


class TestVerdicts:
    def test_the_real_page_matches(self):
        report = diagnose_page(page(), "district", CNR)
        assert report.verdict == MATCH
        assert report.parsed >= 1
        assert report.display_pdf_calls == report.parsed
        assert report.order_tables >= 1
        assert "Interim Orders" in report.headings

    def test_a_page_with_no_orders_section_is_portal_empty(self):
        html = "<html><body><table class='history_table'><tr><td>x</td></tr></table></body></html>"
        report = diagnose_page(html, "district", CNR)
        assert report.verdict == PORTAL_EMPTY
        assert (report.display_pdf_calls, report.order_tables, report.parsed) == (0, 0, 0)

    def test_an_empty_orders_table_is_portal_empty(self):
        html = "<h4>Interim Orders</h4><table class='order_table'><tr><th>Order</th></tr></table>"
        report = diagnose_page(html, "district", CNR)
        assert report.verdict == PORTAL_EMPTY
        assert report.order_tables == 1 and report.order_table_rows == 0

    def test_links_the_parser_cannot_read_are_a_parser_miss(self):
        # A displayPdf() call with too few arguments: the parser skips the row,
        # but the raw page plainly lists an order.
        html = (
            "<h4>Final Orders</h4><table class='order_table'>"
            "<tr><td>1</td><td>01-02-2026</td><td><a onclick=\"displayPdf('only-one')\">Order</a></td></tr>"
            "</table>"
        )
        report = diagnose_page(html, "district", CNR)
        assert report.parsed == 0
        assert report.display_pdf_calls == 1
        assert report.verdict == PARSER_MISS
        assert report.headings == ["Final Orders"]

    def test_order_rows_with_no_link_at_all_are_a_parser_miss_not_empty(self):
        html = (
            "<table class='order_table'>"
            "<tr><td>1</td><td>01-02-2026</td><td>Order</td></tr>"
            "<tr><td>2</td><td>03-02-2026</td><td>Order</td></tr></table>"
        )
        report = diagnose_page(html, "district", CNR)
        assert report.order_table_rows == 2 and report.parsed == 0
        assert report.verdict == PARSER_MISS

    def test_a_table_whose_id_names_orders_counts(self):
        html = "<table id='interimOrders'><tr><td>1</td></tr></table>"
        assert diagnose_page(html, "district", CNR).order_tables == 1

    def test_the_report_holds_counts_and_section_names_never_page_text(self):
        report = diagnose_page(page(), "district", CNR)
        assert PARTY.lower() not in repr(report).lower()

    def test_a_high_court_page_is_read_with_the_hc_parser(self):
        html = (
            "<table class='order_table'><tr><td>1</td><td>Case</td><td>Judge</td><td>01-02-2026</td>"
            "<td><a href='display_pdf.php?filename=x'>Order</a></td></tr></table>"
        )
        report = diagnose_page(html, "high_court", CNR)
        assert (report.parsed, report.display_pdf_php_links, report.verdict) == (1, 1, MATCH)


class TestRun:
    def test_waits_at_least_five_seconds_between_cases_and_never_before_the_first(self):
        sleeps = []
        run_diagnosis(
            [case(1), case(2), case(3)],
            lambda c: "<html></html>",
            sleep=sleeps.append,
            spacing=0.5,  # asking for less is raised to the minimum
        )
        assert sleeps == [MIN_SPACING_SECONDS, MIN_SPACING_SECONDS]
        assert MIN_SPACING_SECONDS == 5

    def test_one_search_per_case(self):
        fetched = []
        run_diagnosis([case(1), case(2)], lambda c: fetched.append(c.id) or "<html></html>", sleep=lambda s: None)
        assert fetched == [1, 2]

    def test_a_failed_search_reports_the_exception_class_only(self):
        class CourtPortalError(Exception):
            pass

        def fetch(c):
            raise CourtPortalError(f"Unrecognized response: <td>{PARTY}</td>")

        ((_, report, error),) = run_diagnosis([case(1)], fetch, sleep=lambda s: None)
        assert report is None
        assert error == "CourtPortalError"
        table = format_table([(case(1), None, error)])
        assert ERROR in table and "CourtPortalError" in table
        assert PARTY not in table

    def test_the_table_shows_the_cnr_prefix_and_no_names(self):
        results = run_diagnosis([case(38)], lambda c: page(), sleep=lambda s: None)
        table = format_table(results)
        assert "TSHC01" in table and CNR not in table
        assert PARTY.lower() not in table.lower()
        assert "MATCH" in table

    def test_the_raw_page_is_saved_only_for_a_parser_miss_and_only_when_asked(self, tmp_path):
        miss = (
            "<table class='order_table'><tr><td>1</td><td>01-02-2026</td>"
            "<td><a onclick=\"displayPdf('x')\">o</a></td></tr></table>"
        )
        written = []
        run_diagnosis([case(7)], lambda c: miss, sleep=lambda s: None, save_dir=None, write=written.append)
        assert written == [] and list(tmp_path.iterdir()) == []

        run_diagnosis([case(7)], lambda c: miss, sleep=lambda s: None, save_dir=tmp_path, write=written.append)
        assert (tmp_path / "case7.html").read_text(encoding="utf-8") == miss
        assert any("case7.html" in line for line in written)

        # A page that matches is never saved.
        run_diagnosis([case(8)], lambda c: page(), sleep=lambda s: None, save_dir=tmp_path, write=written.append)
        assert not (tmp_path / "case8.html").exists()


class TestOrderTableMarker:
    def test_a_bootstrap_table_is_not_an_order_table(self):
        # "table-bordered" contains the letters "order"; it must not count.
        html = "<table class='table table-bordered'><tr><td>x</td></tr></table>"
        assert diagnose_page(html, "district", CNR).order_tables == 0

    def test_the_real_page_has_exactly_one_order_table(self):
        assert diagnose_page(page(), "district", CNR).order_tables == 1
