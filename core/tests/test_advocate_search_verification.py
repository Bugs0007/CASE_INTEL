"""
Regression coverage for the advocate-search result-verification fix.

Root cause (see the prior diagnosis session): District Courts'
"Search by Advocate" grid (casestatus/submitAdvName) is its own 5-column
layout -- Sr No | Case Number | Parties | Advocate Name | View -- not
either of bharat_courts' generic parse_case_status_html's documented 4-
or 7-column shapes. That generic parser's >4-column branch reads fixed
offsets built for a different grid and never looks at the Advocate
column at all, so a case whose registered advocate only shares a name
FRAGMENT with the search (confirmed live 17 Sep 2026: a government
Assistant Public Prosecutor "APPG.Ramesh kumar" matched a search for
"Ramesh Kumar", on totally unrelated criminal matters) was surfaced with
no way for anyone -- human or code -- to tell it apart from a real match.

These tests exercise the fix at the two boundaries that actually matter:
  - parse_advocate_search_html() directly, with fixture HTML that
    mirrors the REAL structure confirmed live (same header text, same
    row/column shape, same onclick-embedded-CNR pattern) but with
    small, deliberately-chosen rows for deterministic assertions -- the
    searched name and a fixture row's PARTY names are always different
    people (petitioner/respondent are litigants, never the advocate),
    so a test that only checked "petitioner looks unrelated to the
    search" would never have caught this bug in the first place. What
    must be checked is the Advocate column specifically.
  - EcourtsProvider._district_search_by_advocate(), mocking _post_ajax
    the same way TestDistrictSearchByAdvocateRetryLogic already does, to
    prove the fix is actually wired into the call site the bug lived in,
    not just correct in isolation.

Run against the OLD code (parse_case_status_html, no verification) every
test in TestParseAdvocateSearchHtml that checks dropping/flagging fails,
because that code path never looks at the Advocate column at all.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.services.court_data.ecourts_parsing import parse_advocate_search_html
from core.services.court_data.ecourts_provider import EcourtsProvider, _TokenSeedingDistrictClient
from core.services.name_matching import advocate_tokens, name_similarity

# ---------------------------------------------------------------------------
# Fixture HTML -- mirrors the real live-captured structure (header text,
# row shape, onclick pattern) confirmed 17 Sep 2026 against real Rangareddy
# (Telangana) District Court complexes, with small/deterministic row
# content chosen for the tests below.
# ---------------------------------------------------------------------------

_HEADER_WITH_ADVOCATE = """
<thead><tr>
<th>Sr No</th>
<th>Case Type/Case Number/Case Year</th>
<th>Petitioner Name versus Respondent Name</th>
<th>Advocate Name</th>
<th>View</th>
</tr></thead>
"""

_HEADER_WITHOUT_ADVOCATE = """
<thead><tr>
<th>Sr No</th>
<th>Case Type/Case Number/Case Year</th>
<th>Petitioner Name versus Respondent Name</th>
<th>View</th>
</tr></thead>
"""


def _row_with_advocate(sr, case_number, petitioner, respondent, advocate, cnr):
    return f"""<tr><td>{sr}</td>
        <td>{case_number}</td>
        <td>{petitioner}<br>Vs</br>{respondent}</td>
        <td>{advocate}</td>
        <td><a onClick="viewHistory(1,'{cnr}',1,'','CScaseNumber',29,9,1290106,'CSAdvName')">View</a></td>
        </tr>"""


def _row_without_advocate(sr, case_number, petitioner, respondent, cnr):
    return f"""<tr><td>{sr}</td>
        <td>{case_number}</td>
        <td>{petitioner}<br>Vs</br>{respondent}</td>
        <td><a onClick="viewHistory(1,'{cnr}',1,'','CScaseNumber',29,9,1290105,'CSAdvName')">View</a></td>
        </tr>"""


def _table(header, *rows):
    return f"<table id='dispTable'>{header}<tbody>{''.join(rows)}</tbody></table>"


# ---------------------------------------------------------------------------
# parse_advocate_search_html
# ---------------------------------------------------------------------------


class TestParseAdvocateSearchHtml:
    def test_matching_advocate_row_is_kept_and_verified(self):
        """The searched name and the row's PARTY names are deliberately
        unrelated people (a litigant is never the advocate) -- only the
        Advocate column should decide the outcome."""
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(
                1, "OS/416/2023", "T. Srivani", "Jillala Varamma",
                "G.Ramesh Kumar", "TSRA110027752023",
            ),
        )
        hits = parse_advocate_search_html(html, advocate_name="Ramesh Kumar")
        assert len(hits) == 1
        hit = hits[0]
        assert hit.cnr_number == "TSRA110027752023"
        assert hit.petitioner == "T. Srivani"
        assert hit.respondent == "Jillala Varamma"
        assert hit.advocate_match_verified is True
        assert hit.matched_advocate_text == "G.Ramesh Kumar"

    def test_nonmatching_advocate_row_is_dropped(self):
        """A real, live-confirmed failure mode: the portal's own grid can
        include a case whose registered advocate shares no real token
        with the search at all. This row must never reach the caller."""
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(
                1, "CC/1/2024", "Mohd Iqbal", "State Bank of India",
                "K. Prasad Rao", "TSRA110000012024",
            ),
        )
        hits = parse_advocate_search_html(html, advocate_name="Ramesh Kumar")
        assert hits == []

    def test_government_prosecutor_name_collision_is_kept_as_a_plausible_match(self):
        """Regression fixture for the live 17 Sep 2026 finding: searching
        "Ramesh Kumar" matched "APPG.Ramesh kumar" -- a government
        Assistant Public Prosecutor, almost certainly a different person
        -- because the Advocate field genuinely contains both query
        tokens. name_similarity cannot (and must not pretend to)
        disambiguate two different real people who share a name; this is
        why the row is surfaced as verified=True WITH the raw matched
        text attached, so a human reviewing before import can see
        "APPG.Ramesh kumar" and recognise it isn't them -- not silently
        dropped (that would hide a plausible match) and not silently
        trusted as identity-confirmed (matched_advocate_text makes the
        raw signal visible)."""
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(
                1, "CC/200014/2014", "PS Shamshabad", "Dusakanti Narsimha",
                "APP<br>G.Ramesh kumar", "TSRA110002662012",
            ),
        )
        hits = parse_advocate_search_html(html, advocate_name="Ramesh Kumar")
        assert len(hits) == 1
        assert hits[0].advocate_match_verified is True
        assert hits[0].matched_advocate_text == "APP G.Ramesh kumar"

    def test_two_advocates_on_separate_lines_do_not_fuse_into_one_token(self):
        """A cell listing two advocates separated by <br> must not be
        glued into "KumarRamesh" -- that would break the token match for
        the second name."""
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(
                1, "OS/1/2024", "A", "B", "A. Kumar<br>Ramesh Naidu", "TSRA110000000009",
            ),
        )
        hits = parse_advocate_search_html(html, advocate_name="Ramesh Naidu")
        assert len(hits) == 1
        assert hits[0].advocate_match_verified is True

    def test_mixed_rows_only_matching_ones_survive(self):
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(1, "OS/1/2024", "A", "B", "G.Ramesh Kumar", "TSRA110000000001"),
            _row_with_advocate(2, "OS/2/2024", "C", "D", "K. Prasad Rao", "TSRA110000000002"),
            _row_with_advocate(3, "OS/3/2024", "E", "F", "B. Ramesh Kumar", "TSRA110000000003"),
        )
        hits = parse_advocate_search_html(html, advocate_name="Ramesh Kumar")
        cnrs = {h.cnr_number for h in hits}
        assert cnrs == {"TSRA110000000001", "TSRA110000000003"}
        assert all(h.advocate_match_verified for h in hits)

    def test_no_advocate_column_is_kept_but_unverified(self):
        """Defensive fallback for a response shape with no Advocate
        column at all (bharat_courts' documented 4-column "Live format")
        -- not reproduced live in this fix's own testing (both real
        complexes checked did have the column), but eCourts is not
        consistent about this shape across every complex/state, so the
        parser must degrade honestly rather than assume the column is
        always there."""
        html = _table(
            _HEADER_WITHOUT_ADVOCATE,
            _row_without_advocate(1, "OS/1/2024", "Budida Srinivas Goud", "Budida Vanaja", "TSRA510006592025"),
        )
        hits = parse_advocate_search_html(html, advocate_name="Ramesh Kumar")
        assert len(hits) == 1
        assert hits[0].advocate_match_verified is False
        assert hits[0].matched_advocate_text is None
        # Never dropped just because it can't be verified.
        assert hits[0].cnr_number == "TSRA510006592025"

    def test_bar_code_search_never_verifies_even_with_advocate_column_present(self):
        """eCourts never exposes a bar code in this grid's free text (see
        party_role.py's docstring for the same limitation) -- advocate_name
        blank (bar-code mode) must never attempt a match, even when an
        Advocate column exists and would score >0 if checked."""
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(1, "OS/1/2024", "A", "B", "G.Ramesh Kumar", "TSRA110000000001"),
        )
        hits = parse_advocate_search_html(html, advocate_name="")
        assert len(hits) == 1
        assert hits[0].advocate_match_verified is False
        # Still surfaced for the human's own eyeballing, just not asserted as verified.
        assert hits[0].matched_advocate_text == "G.Ramesh Kumar"

    def test_blank_advocate_cell_is_unverified_not_dropped(self):
        """The column exists but eCourts left this particular row's cell
        empty -- that's an absence of data, not evidence of a mismatch,
        so it must be kept and flagged unverified, not dropped."""
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(1, "OS/1/2024", "A", "B", "&nbsp;", "TSRA110000000001"),
        )
        hits = parse_advocate_search_html(html, advocate_name="Ramesh Kumar")
        assert len(hits) == 1
        assert hits[0].advocate_match_verified is False
        assert hits[0].matched_advocate_text is None

    def test_no_table_returns_empty_list(self):
        assert parse_advocate_search_html("<div>no table here</div>", advocate_name="Ramesh Kumar") == []

    def test_empty_html_returns_empty_list(self):
        assert parse_advocate_search_html("", advocate_name="Ramesh Kumar") == []

    def test_to_dict_carries_verification_fields(self):
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(1, "OS/1/2024", "A", "B", "G.Ramesh Kumar", "TSRA110000000001"),
        )
        hit = parse_advocate_search_html(html, advocate_name="Ramesh Kumar")[0]
        d = hit.to_dict()
        assert d["advocate_match_verified"] is True
        assert d["matched_advocate_text"] == "G.Ramesh Kumar"
        assert d["cnr_number"] == "TSRA110000000001"


# ---------------------------------------------------------------------------
# name_matching.advocate_tokens (small addition backing the above)
# ---------------------------------------------------------------------------


class TestAdvocateTokens:
    def test_tokenizes_free_text_advocate_field(self):
        assert advocate_tokens("APP\nG.Ramesh kumar") == ("app", "g", "ramesh", "kumar")

    def test_unrelated_names_score_zero(self):
        assert name_similarity(advocate_tokens("Ramesh Kumar"), advocate_tokens("K. Prasad Rao")) == 0

    def test_shared_distinctive_token_scores_above_zero(self):
        assert name_similarity(advocate_tokens("Ramesh Kumar"), advocate_tokens("G. Ramesh Kumar")) > 0

    def test_sharing_only_a_common_surname_scores_zero(self):
        # "Kumar" alone is in name_matching.COMMON_TOKENS -- sharing only
        # that says nothing about identity (same posture as
        # conflict_check.py's use of name_similarity for party names).
        assert name_similarity(advocate_tokens("Anil Kumar"), advocate_tokens("Sunil Kumar")) == 0


# ---------------------------------------------------------------------------
# End-to-end through EcourtsProvider._district_search_by_advocate -- proves
# the fix is wired into the actual call site the bug lived in, not just
# correct in isolation. Mirrors TestDistrictSearchByAdvocateRetryLogic's
# existing mocking pattern in test_advocate_search.py.
# ---------------------------------------------------------------------------


def _mock_district_client(*, captchas, post_ajax_results):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client._init_session = AsyncMock()
    client._setup_court = AsyncMock()
    client._solve_captcha = AsyncMock(side_effect=captchas)
    client._post_ajax = AsyncMock(side_effect=post_ajax_results)
    return client


HIERARCHY = {"state_code": "29", "dist_code": "9", "court_complex_code": "1290106", "est_code": "19"}


class TestDistrictSearchByAdvocateVerification:
    def test_full_pipeline_drops_nonmatching_and_keeps_matching(self):
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(1, "OS/1/2024", "A", "B", "G.Ramesh Kumar", "TSRA110000000001"),
            _row_with_advocate(2, "OS/2/2024", "C", "D", "K. Prasad Rao", "TSRA110000000002"),
        )
        client = _mock_district_client(
            captchas=["abc123"], post_ajax_results=[{"adv_data": html}],
        )
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ), patch("core.services.court_data.ecourts_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = EcourtsProvider()
            results = asyncio.run(
                provider._district_search_by_advocate(
                    HIERARCHY, advocate_name="Ramesh Kumar", bar_state="",
                    bar_code="", bar_year="", status_filter="Both",
                )
            )

        assert [r.cnr_number for r in results] == ["TSRA110000000001"]
        assert results[0].advocate_match_verified is True

    def test_full_pipeline_keeps_unverified_rows_when_no_advocate_column(self):
        html = _table(
            _HEADER_WITHOUT_ADVOCATE,
            _row_without_advocate(1, "OS/1/2024", "Budida Srinivas Goud", "Budida Vanaja", "TSRA510006592025"),
        )
        client = _mock_district_client(
            captchas=["abc123"], post_ajax_results=[{"adv_data": html}],
        )
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ), patch("core.services.court_data.ecourts_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = EcourtsProvider()
            results = asyncio.run(
                provider._district_search_by_advocate(
                    HIERARCHY, advocate_name="Ramesh Kumar", bar_state="",
                    bar_code="", bar_year="", status_filter="Both",
                )
            )

        assert len(results) == 1
        assert results[0].advocate_match_verified is False

    def test_search_by_advocate_public_method_also_verifies(self):
        """search_by_advocate() is the method advocate_search.py's fan-out
        actually calls -- confirm the fix reaches callers through the
        public entry point, not just the internal helper."""
        html = _table(
            _HEADER_WITH_ADVOCATE,
            _row_with_advocate(1, "OS/1/2024", "A", "B", "G.Ramesh Kumar", "TSRA110000000001"),
            _row_with_advocate(2, "OS/2/2024", "C", "D", "K. Prasad Rao", "TSRA110000000002"),
        )
        client = _mock_district_client(
            captchas=["abc123"], post_ajax_results=[{"adv_data": html}],
        )
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ), patch("core.services.court_data.ecourts_provider.asyncio.sleep", new_callable=AsyncMock):
            provider = EcourtsProvider()
            results = provider.search_by_advocate(HIERARCHY, advocate_name="Ramesh Kumar")

        assert [r.cnr_number for r in results] == ["TSRA110000000001"]
