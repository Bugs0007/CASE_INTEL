"""
HTML/PDF response parsing for the eCourts provider.

Split out of ecourts_provider.py: these are pure functions (no bharat_courts
client state, no caching) that turn raw portal HTML/PDF bytes into
CourtCaseData/CourtOrderRecord/HearingRecord. EcourtsProvider imports the
subset it calls directly; parse_complex_code and split_bar_code are also
imported directly by advocate_search.py and views/case_tracking.py. See
ecourts_provider.py's module docstring for the reverse-engineering context
behind these formats (malformed HTML, portal-specific quirks, etc.).
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from bharat_courts.districtcourts.parser import parse_complex_value

# _extract_cnr/_extract_parties are underscore-prefixed vendored internals,
# not bharat_courts' public API -- reused here deliberately, same posture
# as _TokenSeedingDistrictClient reaching into DistrictCourtClient's own
# private _http/_post_ajax/_init_session elsewhere in this integration
# (see ecourts_provider.py's module docstring). Both already correctly
# handle the live portal's HTML quirks (malformed "<br>Vs</br>", onclick-
# embedded CNRs) -- reimplementing them here would just risk silently
# drifting from behavior already verified live.
from bharat_courts.districtcourts.parser import _extract_cnr, _extract_parties

from core.services.court_data.models import AdvocateSearchHit, CourtCaseData, CourtOrderRecord, HearingRecord
from core.services.name_matching import advocate_tokens, name_similarity

logger = logging.getLogger(__name__)


DATE_FORMAT = "%d-%m-%Y"


def _parse_date(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in (DATE_FORMAT, "%d-%b-%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


_CASE_NUMBER_PREFIX_SPACE_RE = re.compile(r"^([A-Za-z]+)\s+(?=/)")


def normalize_case_number(value: str | None) -> str:
    """Collapse a stray space between a case-type prefix and the slash that
    follows it (e.g. "WP /26147/2026" -> "WP/26147/2026") -- a formatting
    quirk of the source portal HTML cell, not something _clean() removes
    (it only collapses whitespace *runs*, deliberately leaving single
    internal spaces alone since it's shared with fields like party names
    where internal spacing is meaningful). Any other internal spacing in
    the value is left untouched."""
    cleaned = _clean(value)
    if not cleaned:
        return cleaned
    return _CASE_NUMBER_PREFIX_SPACE_RE.sub(r"\1", cleaned)


_LABEL_PUNCT_RE = re.compile(r"[.:]")


def _normalize_label(text: str | None) -> str:
    """_clean() plus lowercasing and stripping the punctuation eCourts'
    detail-table labels are inconsistent about ("Registration No" vs a
    hypothetical "Registration No." / "Registration No:") -- used ONLY
    for matching against _DETAIL_LABELS, never for cell VALUES, which can
    contain meaningful punctuation (case numbers, dates) that must not be
    stripped."""
    return _LABEL_PUNCT_RE.sub("", _clean(text)).lower()


_ORDINAL_RE = re.compile(r"(\d+)(st|nd|rd|th)\b", re.I)


def _normalize_ordinal_date(text: str) -> str:
    """'29th December 2023' -> '29 December 2023', parseable by _parse_date."""
    return _ORDINAL_RE.sub(r"\1", text)


_BAR_CODE_RE = re.compile(r"^([A-Za-z]{2,3})/(\d+)/(\d{4})$")


def split_bar_code(bar_code: str) -> tuple[str, str, str]:
    """Split a "STATE/NUMBER/YEAR" bar registration number (e.g.
    "MAH/1234/2015", per the portal's own help text) into the three
    separate fields its Advocate-search form actually expects
    (adv_bar_state/adv_bar_code/adv_bar_year) -- confirmed live, the
    portal does NOT accept one combined string.

    Raises ValueError if the format doesn't match."""
    match = _BAR_CODE_RE.match(bar_code.strip())
    if not match:
        raise ValueError(
            f"Bar code {bar_code!r} does not match the expected STATE/NUMBER/YEAR "
            "format (e.g. MAH/1234/2015)."
        )
    return match.group(1).upper(), match.group(2), match.group(3)


def _district_advocate_search_form(
    *,
    state_code: str,
    dist_code: str,
    court_complex_code: str,
    est_code: str = "",
    advocate_name: str = "",
    bar_state: str = "",
    bar_code: str = "",
    bar_year: str = "",
    status_filter: str = "Both",
    captcha: str,
) -> dict[str, str]:
    """Form data for the District Courts "Search by Advocate" tab
    (casestatus/submitAdvName) -- not in bharat_courts.districtcourts.
    endpoints, discovered live (see module docstring). radAdvt selects
    Advocate Name ("1") vs Bar Code ("2"); exactly one of advocate_name or
    the bar_* trio should be populated by the caller."""
    is_bar_code = bool(bar_state or bar_code or bar_year)
    return {
        "radAdvt": "2" if is_bar_code else "1",
        "advocate_name": advocate_name,
        "adv_bar_state": bar_state,
        "adv_bar_code": bar_code,
        "adv_bar_year": bar_year,
        "case_status": status_filter,
        "adv_captcha_code": captcha,
        "state_code": state_code,
        "dist_code": dist_code,
        "court_complex_code": court_complex_code,
        "est_code": est_code,
        "case_type": "",
    }


_ADVOCATE_HEADER_RE = re.compile(r"\badvocate\b", re.I)


def parse_advocate_search_html(
    html: str, *, advocate_name: str = "",
) -> list[AdvocateSearchHit]:
    """Parse casestatus/submitAdvName's "adv_data" HTML, dropping rows
    that don't actually match the search and flagging the rest as
    verified or not.

    advocate_name blank means this was a bar_code search -- there is
    nothing here to match a bar code against (see the docstring below),
    so every row is kept unverified regardless of whether an Advocate
    column exists.

    Why this exists instead of reusing bharat_courts' generic
    parse_case_status_html (which every OTHER search on this file still
    uses for case-number/party-name grids): confirmed live 17 Sep 2026
    against two real Rangareddy (Telangana) court complexes that the
    "Search by Advocate" grid is its own, THIRD column layout --
    Sr No | Case Number | Parties | Advocate Name | View -- not either of
    parse_case_status_html's documented 4- or 7+-column shapes. Both live
    samples had a real, populated "Advocate Name" <th>, and the portal
    DOES filter server-side on it: a nonsense name returned zero rows in
    the same complex that returned real matches for a real name. So this
    was never "the portal isn't filtering." It was that
    parse_case_status_html's generic >4-column branch reads fixed
    offsets built for a different grid (Filing Date/Reg Date/Status) and
    never looks at the Advocate column at all, so nothing downstream
    could tell a genuine match from a same-surname stranger -- confirmed
    live: searching "Ramesh Kumar" matched "APPG.Ramesh kumar" (a
    government Assistant Public Prosecutor appearing on unrelated
    criminal matters), "B. Ramesh Kumar", and a plain "Ramesh kumar" all
    in one complex. eCourts' own name matching is a loose, real
    token/substring match -- not broken, just unable to distinguish two
    different people who share a name fragment -- which is exactly what
    name_similarity below is for.

    The Advocate column is located by HEADER TEXT ("Advocate" in a <th>),
    not a hardcoded index or column count: eCourts is not consistent
    about this shape across every complex/state (same reasoning as
    core/services/cause_list/telangana_hc.py's per-document column
    detection), so a complex that genuinely has no such column must fall
    back cleanly instead of misreading some other field as if it were
    the advocate name.

    Rows are DROPPED when an Advocate column exists, advocate_name was
    given, and name_similarity(...) scores 0 -- no real, non-generic name
    token in common, i.e. eCourts matched on something our own filter
    can't defend. Rows are KEPT with advocate_match_verified=False
    (never dropped) when there's nothing to check them against: no
    Advocate column in this response shape, a blank cell, or a bar_code
    search (eCourts never exposes bar codes in this grid -- see
    party_role.py's docstring for the same gap). Pretending those are
    verified would be worse than admitting they aren't.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if not table:
        return []

    header_cells = []
    thead = table.find("thead")
    header_row = thead.find("tr") if thead else table.find("tr")
    if header_row is not None:
        header_cells = header_row.find_all("th")

    advocate_col_index = None
    for index, cell in enumerate(header_cells):
        if _ADVOCATE_HEADER_RE.search(_clean(cell.get_text())):
            advocate_col_index = index
            break

    can_check_name = bool(advocate_name) and advocate_col_index is not None
    query_tokens = advocate_tokens(advocate_name) if advocate_name else ()
    # A common name can yield tens of thousands of rows (one live response
    # was 25.7MB) that repeat the same few advocate strings -- score each
    # distinct string once, not once per row.
    matches_by_text: dict[str, bool] = {}

    hits: list[AdvocateSearchHit] = []
    for row in table.find_all("tr"):
        if row.find("th"):
            continue  # header row, or a court-name group separator row
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        case_number = normalize_case_number(cols[1].get_text())
        petitioner, respondent = _extract_parties(cols[2])
        cnr = _extract_cnr(row)

        advocate_text = None
        if advocate_col_index is not None and advocate_col_index < len(cols):
            # Space-joined: the live markup is "APP<br>G.Ramesh kumar", and a
            # bare get_text() fuses that to "APPG.Ramesh kumar" -- worse, a
            # cell listing two advocates on separate lines would fuse their
            # tokens together and defeat the name match.
            advocate_text = _clean(cols[advocate_col_index].get_text(" ")) or None

        verified = False
        if can_check_name and advocate_text:
            if advocate_text not in matches_by_text:
                matches_by_text[advocate_text] = (
                    name_similarity(query_tokens, advocate_tokens(advocate_text)) > 0
                )
            if not matches_by_text[advocate_text]:
                continue  # portal matched something the Advocate field doesn't back up
            verified = True

        hits.append(
            AdvocateSearchHit(
                case_number=case_number,
                case_type=case_number.split("/")[0] if "/" in case_number else "",
                cnr_number=cnr,
                petitioner=petitioner,
                respondent=respondent,
                advocate_match_verified=verified,
                matched_advocate_text=advocate_text,
            )
        )
    return hits


_DETAIL_LABELS = {
    "first hearing date": "first_hearing_date",
    "next hearing date": "next_hearing_date",
    "next date": "next_hearing_date",
    "case status": "case_status",
    "nature of disposal": "nature_of_disposal",
    "coram": "court_and_judge",
    "court number and judge": "court_and_judge",
    "case stage": "case_stage",
    # e.g. "Registration Number" / "Registration No" / "Registration No." --
    # two keys because "registration no" is NOT a substring of
    # "registration number" ("number" starts with "nu", not "no").
    # Deliberately NOT a bare "registration" key -- eCourts case-history
    # pages also have a separate "Registration Date" row, which a bare
    # prefix would wrongly capture into this field. This is the portal's
    # own case number (e.g. "WP/23998/2026"), NOT the CNR -- see
    # CourtCaseData.registration_number's docstring for why the two must
    # never be conflated.
    "registration number": "registration_number",
    "registration no": "registration_number",
}

_PARTY_NUMBERING_RE = re.compile(r"^\d+\)\s*")


def _extract_first_party(soup: BeautifulSoup, class_name: str) -> str:
    """Both portals render party lists under a ``Petitioner_Advocate_table``/
    ``Respondent_Advocate_table``-classed element (District: ``<ul>``, HC
    Services: ``<span>``) with one or more "N) Name" entries separated by
    ``<br>``, interleaved with "Advocate- ..." lines. Returns just the
    first party's name -- enough for a human to recognize the case, not a
    full structured list (CourtCaseData has a single string field here,
    matching how the case-number/party-search flow already populates it)."""
    el = soup.find(class_=class_name)
    if el is None:
        return ""
    for line in el.get_text("\n").split("\n"):
        line = _clean(line)
        if not line or line.lower().startswith("advocate"):
            continue
        return _PARTY_NUMBERING_RE.sub("", line).strip()
    return ""


_ADVOCATE_PREFIX_RE = re.compile(r"^advocate\s*[-:]\s*", re.I)


def _extract_advocates(soup: BeautifulSoup, class_name: str) -> list[str]:
    """Sibling of _extract_first_party: collects the "Advocate- ..." lines
    that element interleaves with party names, instead of discarding them
    (req: capture raw per-party advocate names for party-role detection).
    Returns [] when the element has no advocate lines -- common; many
    cases list no advocate, or the party is self-represented."""
    el = soup.find(class_=class_name)
    if el is None:
        return []
    advocates = []
    for line in el.get_text("\n").split("\n"):
        line = _clean(line)
        if not line or not line.lower().startswith("advocate"):
            continue
        name = _ADVOCATE_PREFIX_RE.sub("", line).strip()
        if name:
            advocates.append(name)
    return advocates


def parse_case_history_html(html: str) -> CourtCaseData | None:
    """Parse an eCourts case-history response into a partial CourtCaseData.

    ``cnr`` is left blank here -- callers always already know it (either
    from the search step's result, or because CNR was the search input
    itself) and set it directly; the CNR text embedded in this HTML is
    inconsistently formatted (HC Services renders it with hyphens, e.g.
    "HBHC01-000377-2010", unlike the hyphen-free CNR used everywhere else
    including this same response's onclick handlers).

    Returns None if the response is empty or an error page -- callers
    treat that as "history unavailable" without failing the whole fetch,
    since case identity/parties are already known from the search step.
    """
    if not html or len(html.strip()) < 20:
        return None
    if "THERE IS AN ERROR" in html or "Invalid Request" in html:
        logger.warning("Case-history endpoint returned an error page: %r", html.strip()[:200])
        return None

    soup = BeautifulSoup(html, "lxml")
    data = CourtCaseData(cnr="")

    # Details table: HC Services renders label+value as <td>; District
    # Courts renders the label as <th scope='row'> -- both are checked.
    # A row isn't always exactly one label/value pair: confirmed live
    # against CNR HBHC010536082026 (Telangana HC), the Filing/Registration
    # Number+Date rows each pack TWO pairs into one <tr> (4 cells: label,
    # value, label, value) -- a plain "len(cells) != 2: skip" throws the
    # whole row away before the label is ever read, which is why
    # registration_number came back empty even though the label text
    # itself ("Registration Number") matches _DETAIL_LABELS exactly. Walk
    # the cells in (label, value) strides instead, so this also covers
    # any row bundling 3+ pairs (6, 8... cells) the same way.
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        for i in range(0, len(cells) - 1, 2):
            label = _normalize_label(cells[i].get_text())
            value = _clean(cells[i + 1].get_text())
            if not label or not value:
                continue
            for key, field_name in _DETAIL_LABELS.items():
                if key in label:
                    if field_name in ("next_hearing_date", "first_hearing_date"):
                        parsed = _parse_date(_normalize_ordinal_date(value))
                        if parsed:
                            setattr(data, field_name, parsed)
                    elif not getattr(data, field_name):
                        setattr(data, field_name, value)
                    break

    if data.registration_number:
        data.registration_number = normalize_case_number(data.registration_number)

    data.petitioner = _extract_first_party(soup, "Petitioner_Advocate_table")
    data.respondent = _extract_first_party(soup, "Respondent_Advocate_table")

    petitioner_advocates = _extract_advocates(soup, "Petitioner_Advocate_table")
    respondent_advocates = _extract_advocates(soup, "Respondent_Advocate_table")
    if petitioner_advocates or respondent_advocates:
        data.party_advocate_data = {
            "petitioner_advocates": petitioner_advocates,
            "respondent_advocates": respondent_advocates,
        }

    # District Courts' CNR-search response has a court-name heading; HC
    # Services' doesn't expose an equivalent single element here, so
    # court_name stays whatever the caller already set (or blank).
    ch_heading = soup.find(id="chHeading")
    if ch_heading is not None:
        heading_text = _clean(ch_heading.get_text())
        if heading_text:
            data.court_name = heading_text

    # Hearing-history table: match by CSS class, not a header-keyword
    # heuristic (which previously matched the wrong table -- see module
    # docstring).
    table = soup.find("table", class_="history_table")
    if table is None:
        for candidate in soup.find_all("table"):
            if "history" in " ".join(candidate.get("class", [])).lower():
                table = candidate
                break

    if table is not None:
        header_cells = table.find_all("th")
        col_names = [_clean(c.get_text()).lower() for c in header_cells]

        def _col_index(*keywords: str) -> int | None:
            for idx, name in enumerate(col_names):
                if any(kw in name for kw in keywords):
                    return idx
            return None

        idx_causelist = _col_index("cause list")
        idx_judge = _col_index("judge")
        idx_business = _col_index("business")
        idx_hearing = _col_index("hearing date")
        idx_purpose = _col_index("purpose")

        for row in table.find_all("tr"):
            # The live HTML is malformed: the Orders table is missing a
            # closing </table> and parses as nested inside history_table.
            # Skip rows that actually belong to that nested table.
            if row.find_parent("table") is not table:
                continue
            cols = row.find_all("td")
            if not cols or row.find("th"):
                continue
            row_text = [_clean(c.get_text()) for c in cols]

            def _get(idx: int | None) -> str:
                return row_text[idx] if idx is not None and idx < len(row_text) else ""

            hearing = HearingRecord(
                hearing_date=_parse_date(_get(idx_hearing)),
                business_date=_parse_date(_get(idx_business)),
                purpose=_get(idx_purpose),
                judge=_get(idx_judge),
                cause_list_type=_get(idx_causelist),
            )
            if any([hearing.hearing_date, hearing.business_date, hearing.purpose, hearing.judge]):
                data.hearing_history.append(hearing)

    return data


# ---------------------------------------------------------------------------
# Orders parsing (Phase B order-fetch spike, ~/bharat-env/order_fetch_spike.py)
#
# HC Services: the CNR-search response embeds an Orders table
# (class="order_table"): Order Number | Order on | Judge | Order Date |
# Order Details, where the details cell holds an <a href="cases/
# display_pdf.php?filename=<encrypted>&..."> link. Verified live: the link
# downloads a real PDF in the SAME session (application/pdf, 0.6s) but
# returns an "Orders is not uploaded" error page from a fresh session --
# the encrypted filename token is session-bound, hence the re-search in
# download_order().
#
# District Courts: the same CNR-search response is expected to carry
# displayPdf(normal_v, case_val, court_code, filename, appFlag) onclick
# links when orders are uploaded (per the live portal's own components.js
# displayPdf(), which POSTs home/display_pdf and GETs the returned path).
# NOT yet observed live -- every real case checked in the spike (the
# tracked case + 3 others at the same court) listed zero orders, so the
# district download leg below is best-effort: built from the portal's own
# JS, exercised only when a district case with uploaded orders appears.
# ---------------------------------------------------------------------------

_HC_ORDERS_BASE = "https://hcservices.ecourts.gov.in/hcservices/"
_DC_ORDERS_BASE = "https://services.ecourts.gov.in/ecourtindia_v6/"

_DC_DISPLAYPDF_RE = re.compile(
    r"""displayPdf\(\s*'?([^,'\)]*)'?\s*,\s*'([^']*)'\s*,\s*'?([^,'\)]*)'?\s*,\s*'([^']*)'\s*(?:,\s*'([^']*)')?\s*\)"""
)


def _strip_pdf_prefix(raw: bytes) -> bytes:
    """Both portals have been observed to prepend junk (a UTF-8 BOM on HC
    Services) before the %PDF magic; strip anything before it."""
    idx = raw.find(b"%PDF-")
    return raw[idx:] if idx > 0 else raw


def _parse_hc_orders(html: str, cnr: str) -> list[tuple[CourtOrderRecord, str]]:
    """Parse the HC Services order_table into (record, href) pairs.

    href is the session-bound relative display_pdf.php link -- only valid
    for the session that produced `html`.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="order_table")
    if table is None:
        return []

    results: list[tuple[CourtOrderRecord, str]] = []
    for row in table.find_all("tr"):
        link = row.find("a", href=re.compile(r"display_pdf\.php"))
        if link is None:
            continue
        cells = [_clean(c.get_text()) for c in row.find_all("td")]
        # Columns: Order Number | Order on | Judge | Order Date | Order Details
        order_number = cells[0] if len(cells) > 0 else ""
        order_on = cells[1] if len(cells) > 1 else ""
        judge = cells[2] if len(cells) > 2 else ""
        order_date = _parse_date(cells[3]) if len(cells) > 3 else None
        if not order_number:
            continue
        record = CourtOrderRecord(
            cnr=cnr,
            order_number=order_number,
            order_date=order_date,
            description=f"Order {order_number} on {order_on}".strip(),
            judge=judge,
        )
        results.append((record, link.get("href", "")))
    return results


def _parse_district_orders(html: str, cnr: str) -> list[tuple[CourtOrderRecord, dict]]:
    """Parse district-court order rows into (record, displayPdf-args) pairs.

    Best-effort (see module comment above): matches rows containing a
    displayPdf(...) onclick and reads order number/date from the row's
    cells by position, mirroring the HC layout. Returns [] when no
    displayPdf links exist -- the verified-common case.
    """
    if "displayPdf" not in html:
        return []
    soup = BeautifulSoup(html, "lxml")
    results: list[tuple[CourtOrderRecord, dict]] = []
    for row in soup.find_all("tr"):
        onclick_el = row.find(attrs={"onclick": re.compile(r"displayPdf\(")})
        if onclick_el is None:
            link = row.find("a", href=re.compile(r"displayPdf\("))
            onclick_el = link
        if onclick_el is None:
            continue
        target = onclick_el.get("onclick") or onclick_el.get("href") or ""
        match = _DC_DISPLAYPDF_RE.search(target)
        if not match:
            continue
        normal_v, case_val, court_code, ofilename, app_flag = match.groups()
        cells = [_clean(c.get_text()) for c in row.find_all("td")]
        order_number = cells[0] if cells else ""
        order_date = None
        for cell in cells:
            order_date = _parse_date(cell)
            if order_date:
                break
        if not order_number:
            continue
        record = CourtOrderRecord(
            cnr=cnr,
            order_number=order_number,
            order_date=order_date,
            description=f"Order {order_number}" + (f" on {case_val}" if case_val else ""),
        )
        results.append((
            record,
            {
                "normal_v": normal_v or "",
                "case_val": case_val or "",
                "court_code": court_code or "",
                "filename": ofilename or "",
                "appFlag": app_flag or "",
            },
        ))
    return results


_VIEWHISTORY_RE = re.compile(
    r"viewHistory\((\d+),\s*'([A-Z]{4}\d{12,})'\s*,\s*'?([^,']*)'?\s*,"
    r"\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'([^']*)'"
)


def _extract_view_history_args(raw_html: str, target_cnr: str) -> dict | None:
    """Recover the numeric case_no District Courts' viewHistory() needs,
    embedded in the search result row's onclick attribute alongside the
    CNR -- not exposed anywhere on CaseInfo."""
    for match in _VIEWHISTORY_RE.finditer(raw_html):
        case_no, cnr, court_code, hideparty, search_flag, state_code, dist_code, complex_code, search_by = match.groups()
        if cnr == target_cnr:
            return {
                "case_no": case_no,
                "cino": cnr,
                "court_code": court_code,
                "hideparty": hideparty,
                "search_flag": search_flag,
                "state_code": state_code,
                "dist_code": dist_code,
                "court_complex_code": complex_code,
                "search_by": search_by,
            }
    return None


def parse_complex_code(raw_value: str) -> tuple[str, str]:
    """Split a list_complexes() dropdown value ("code@est_codes@flag")
    into (complex_code, first_est_code)."""
    complex_code, est_codes, _needs_est = parse_complex_value(raw_value)
    return complex_code, (est_codes[0] if est_codes else "")

