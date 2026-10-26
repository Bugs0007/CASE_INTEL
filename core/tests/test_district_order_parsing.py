"""District order-listing parser (ecourts_parsing._parse_district_orders).

Built on the one real captured District Courts CNR page that carries an
Interim Orders table, with variants made by editing that page -- no live
portal access. The variants are the markup shapes the old parser dropped
silently or collided on.
"""

import logging
from pathlib import Path

import pytest

from core.services.court_data import CourtOrderRecord
from core.services.court_data.ecourts_parsing import _displaypdf_args, _parse_district_orders

PAGE = (
    Path(__file__).parent
    / "fixtures/causelists/district_ecourts/cnr_case_page/TSHC010030082026.html"
)
CNR = "TSHC010030082026"
PARTY = "PEOPLE MEDIA FACTORY"  # a party name on the page: must never reach a log line

_LINK = "onclick=displayPdf('cl+sGJoSJ58oyVespa8VHg==','DTDcV7locz+5/g4DRg7ukw==','1Wa2LjH5w7zcPVzbT+mRgw==','wWb/gxKYhtwW/QxZVcsQz1aICBjzNpO4KjnUNmHWWLlnWDES02n4YyMV2dpu6oaM','') >"


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def caplog():
    """The "core" logger doesn't propagate (settings.LOGGING), so pytest's own
    caplog never sees it; attach a handler to the parser's logger directly."""
    logger = logging.getLogger("core.services.court_data.ecourts_parsing")
    handler = _Records()
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


def page() -> str:
    html = PAGE.read_text(encoding="utf-8")
    assert _LINK in html and PARTY.lower() in html.lower()
    return html


def orders(html: str):
    return [record for record, _args in _parse_district_orders(html, CNR)]


def final_block(html: str) -> str:
    """The Interim Orders heading + table, relabelled as a Final Orders one."""
    start = html.index("<h3 class='h2class' align='center'  id='orderheading'>")
    end = html.index("</table>", html.index('class="order_table')) + len("</table>")
    return html[start:end].replace("Interim Orders", "Final Orders").replace("orderheading", "finalheading")


class TestCapturedPage:
    def test_finds_the_real_interim_order(self):
        (record,) = orders(page())
        assert record.order_number == "1"
        assert record.order_date.isoformat() == "2026-09-15"
        assert record.section == "interim"
        assert record.description == "Interim order 1"

    def test_args_carry_the_portals_download_parameters(self):
        ((_, args),) = _parse_district_orders(page(), CNR)
        assert args["filename"].startswith("wWb/gxKYhtw")
        assert args["appFlag"] == ""
        assert set(args) == {"normal_v", "case_val", "court_code", "filename", "appFlag"}

    def test_interim_key_is_the_legacy_key(self):
        # Rows saved before sections existed carry this exact key.
        (record,) = orders(page())
        assert record.dedup_key == f"{CNR}:1:2026-09-15"

    def test_description_no_longer_embeds_the_portals_encrypted_token(self):
        (record,) = orders(page())
        assert "DTDcV7" not in record.description


class TestLinkForms:
    def test_double_quoted_attribute_and_double_quoted_args(self):
        html = page().replace(
            _LINK, """onclick='displayPdf("a1","b2","c3","d4","")' >"""
        )
        ((record, args),) = _parse_district_orders(html, CNR)
        assert (record.order_number, args["filename"], args["normal_v"]) == ("1", "d4", "a1")

    def test_quoted_attribute_with_single_quoted_args(self):
        html = page().replace(_LINK, """onclick="displayPdf('a1','b2','c3','d4','')" >""")
        ((_, args),) = _parse_district_orders(html, CNR)
        assert args["filename"] == "d4"

    def test_bare_unquoted_args_and_four_args_only(self):
        html = page().replace(_LINK, "onclick=displayPdf(a1,b2,c3,d4) >")
        ((_, args),) = _parse_district_orders(html, CNR)
        assert (args["normal_v"], args["filename"], args["appFlag"]) == ("a1", "d4", "")

    def test_javascript_href_form(self):
        # The anchor already carries href='#'; the javascript: form replaces it.
        html = page().replace("href='#' aria-label=", "aria-label=").replace(
            _LINK, "href=\"javascript:displayPdf('a1','b2','c3','d4','')\" >"
        )
        assert len(orders(html)) == 1

    def test_args_helper_rejects_a_call_with_too_few_arguments(self):
        assert _displaypdf_args("displayPdf('a','b')") is None
        assert _displaypdf_args("viewBusiness('a','b','c','d')") is None
        assert _displaypdf_args("displayPdf('a','b','c','d')") == ["a", "b", "c", "d"]


class TestEmptyNumberCell:
    def test_row_with_a_link_is_kept_under_a_date_based_number(self):
        html = page().replace("<td>&nbsp;&nbsp;1</td>", "<td>&nbsp;&nbsp;</td>")
        (record,) = orders(html)
        assert record.order_number == "2026-09-15"
        assert record.dedup_key == f"{CNR}:2026-09-15:2026-09-15"

    def test_two_numberless_rows_on_one_date_stay_distinct(self):
        html = page().replace("<td>&nbsp;&nbsp;1</td>", "<td></td>")
        row_start = html.index("<tr><td></td>")
        row_end = html.index("</tr>", row_start) + len("</tr>")
        row = html[row_start:row_end]
        html = html[:row_end] + row + html[row_end:]
        numbers = sorted(o.order_number for o in orders(html))
        assert numbers == ["2026-09-15", "2026-09-15-2"]


class TestInterimAndFinal:
    def test_same_number_and_date_do_not_collide(self):
        html = page()
        end = html.rindex("</table>")
        both = html[:end] + "</table>" + final_block(html) + html[end:]
        records = orders(both)
        assert sorted(r.section for r in records) == ["final", "interim"]
        keys = {r.dedup_key for r in records}
        assert keys == {f"{CNR}:1:2026-09-15", f"{CNR}:1:2026-09-15:final"}

    def test_final_only_page_is_labelled_final(self):
        html = page().replace("Interim Orders", "Final Orders")
        (record,) = orders(html)
        assert record.section == "final"
        assert record.dedup_key.endswith(":final")
        assert record.description == "Final order 1"

    def test_section_changes_only_the_final_key(self):
        interim = CourtOrderRecord(cnr=CNR, order_number="1", section="interim")
        legacy = CourtOrderRecord(cnr=CNR, order_number="1")
        final = CourtOrderRecord(cnr=CNR, order_number="1", section="final")
        assert interim.dedup_key == legacy.dedup_key == f"{CNR}:1:unknown"
        assert final.dedup_key == f"{CNR}:1:unknown:final"


class TestNeverSilent:
    def test_unparseable_link_in_an_orders_section_warns_with_counts_only(self, caplog):
        html = page().replace(_LINK, "onclick=displayPdf('only','two') >")
        assert orders(html) == []
        (warning,) = [r for r in caplog.records if r.levelno == logging.WARNING]
        message = warning.getMessage()
        assert CNR in message and "rows_unparsed=1" in message and "order_tables=1" in message
        assert PARTY.lower() not in message.lower()

    def test_no_displaypdf_at_all_but_rows_in_the_table_warns(self, caplog):
        html = page().replace(_LINK, "onclick=somethingElse('x') >")
        assert orders(html) == []
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1 and "data_rows=1" in warnings[0].getMessage()

    def test_empty_orders_section_is_info_not_warning(self, caplog):
        html = (
            "<html><body><h3 id='orderheading'>Interim Orders </h3>"
            "<table class='order_table table'><thead><tr><th>Order Number</th></tr></thead></table></body></html>"
        )
        assert orders(html) == []
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("orders section is empty" in r.getMessage() for r in caplog.records)

    def test_page_without_any_orders_markup_is_quiet(self, caplog):
        assert orders("<html><body><table class='history_table'></table></body></html>") == []
        assert not caplog.records
