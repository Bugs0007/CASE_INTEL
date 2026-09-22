"""
Regression coverage for case-number formatting inconsistency (UI/UX pass,
item 6): the eCourts portal's own HTML occasionally puts a stray space
between a case-type prefix and the slash that follows it, e.g.
"WP /26147/2026" instead of "WP/26147/2026" -- confirmed by comparing
against sibling cases from the same source that don't have it. _clean()
deliberately doesn't strip single internal spaces (shared with fields like
party names where that spacing is meaningful), so a dedicated
normalize_case_number() collapses it specifically for case numbers, at
both places raw eCourts values become Case.case_number:
parse_case_history_html's registration_number and
parse_advocate_search_html's case_number.
"""

from core.services.court_data.ecourts_parsing import (
    normalize_case_number,
    parse_advocate_search_html,
    parse_case_history_html,
)


class TestNormalizeCaseNumber:
    def test_collapses_space_before_prefix_slash(self):
        assert normalize_case_number("WP /26147/2026") == "WP/26147/2026"

    def test_leaves_already_clean_value_unchanged(self):
        assert normalize_case_number("WP/23998/2026") == "WP/23998/2026"

    def test_leaves_other_internal_spacing_untouched(self):
        # Only the prefix/slash boundary is collapsed -- this helper isn't
        # a general whitespace stripper.
        assert normalize_case_number("OS 138 / 2008") == "OS 138 / 2008"

    def test_blank_input(self):
        assert normalize_case_number("") == ""
        assert normalize_case_number(None) == ""

    def test_collapses_whitespace_runs_too(self):
        assert normalize_case_number("WP   /26147/2026") == "WP/26147/2026"


class TestRegistrationNumberNormalizedOnParse:
    def test_stray_space_after_prefix_is_collapsed(self):
        html = """
        <table>
          <tr>
            <td>Registration Number</td><td>WP /26147/2026</td>
            <td>Registration Date</td><td>06-08-2026</td>
          </tr>
        </table>
        """
        data = parse_case_history_html(html)

        assert data is not None
        assert data.registration_number == "WP/26147/2026"


class TestAdvocateSearchCaseNumberNormalizedOnParse:
    def test_stray_space_after_prefix_is_collapsed(self):
        html = """<table id='dispTable'><tbody>
            <tr><td>1</td>
            <td>WP /26147/2026</td>
            <td>T. Srivani<br>Vs</br>Jillala Varamma</td>
            <td><a onClick="viewHistory(1,'TSRA110027752023',1,'','CScaseNumber',29,9,1290106,'CSAdvName')">View</a></td>
            </tr>
        </tbody></table>"""

        hits = parse_advocate_search_html(html, advocate_name="")

        assert len(hits) == 1
        assert hits[0].case_number == "WP/26147/2026"
