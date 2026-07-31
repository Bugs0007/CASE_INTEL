"""Parser + fetcher for the High Court for the State of Telangana daily
cause list.

DOM this targets (verified against a real saved list for 3 Aug 2026,
core/tests/fixtures/causelists/):

    <table id="dataTable">
      <thead> ... COURT NO. 1 ... To be heard on Monday the 3rd day of
              August 2026 ... DAILY LIST ...
              Sl.No. | Case | Party Details | Petitioner Advocate |
              Respondent Advocate | District/Remarks </thead>
      <tbody>                            <- ONE PER ITEM, not one per table
        <tr><td colspan=6><span class="stage-name">FOR ADMISSION ...</span></td></tr>
        <tr>
          <td>3</td>                                        <- item/serial
          <td><a id="caseNumber" data-case-id="WA/789/2026">WA/789/2026</a>
              <div data-case-id="IA 1/2026(...)">...</div>   <- connected IAs
          </td>
          <td>PETITIONER vs RESPONDENT</td>
          ...
        </tr>
      </tbody>
      ... x62
    </table>

The per-item <tbody> repetition is the surprising part (the page is a
Thymeleaf template rendered server-side, and each item gets its own
tbody with its own copy of the stage header), so iterate tbodies rather
than rows.

One list document = one court hall = one date. A run that needs several
halls fetches several documents.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from bs4 import BeautifulSoup

from .exceptions import CauseListNotConfiguredError, CauseListParseError

logger = logging.getLogger(__name__)

COURT_KEY = "telangana_hc"
COURT_LABEL = "High Court for the State of Telangana"

_COURT_HALL_RE = re.compile(r"COURT\s*NO\.?\s*([0-9]+)", re.IGNORECASE)
# "To be heard on Monday the 3rd day of August 2026 (AT 10:30 AM ...)"
_LIST_DATE_RE = re.compile(
    r"To\s+be\s+heard\s+on\s+\w+\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
)
_LIST_TYPE_RE = re.compile(
    r"\b((?:DAILY|SUPPLEMENTARY|ADDITIONAL|WEEKLY|SPECIAL)\s+LIST)\b", re.IGNORECASE
)

# "WA/102/2026", "W.A./102/2026", "WA 102 of 2026", "WA-102-2026", and
# parenthesised types as printed by this court: "WP(PIL)/58/2023".
_CASE_TOKEN_RE = re.compile(
    r"^\s*([A-Za-z][A-Za-z.()\s]{0,20}?)\s*[/\-\s]\s*(\d{1,7})\s*(?:/|-|\s+of\s+|\s+)\s*(\d{4})\s*$",
    re.IGNORECASE,
)

# "WA/36270/2026/(Filing No.)" -- a matter listed by its FILING number
# because it hasn't been registered yet. Filing and registration numbers
# are separate series that freely collide, so these are parsed but kept
# out of the matching index (see CauseListItem.is_filing_number).
_FILING_NUMBER_SUFFIX_RE = re.compile(r"\s*/?\s*\(\s*filing\s*no\.?\s*\)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class CauseListItem:
    """One listed matter."""

    item_number: str
    case_token: str
    case_type: str
    case_serial: str
    case_year: str
    stage: str = ""
    parties: str = ""
    # Connected IA/interlocutory entries shown under the main case. Kept
    # for display only -- never matched on, since an IA number is not the
    # main case's identity and matching it would attach the wrong item
    # number to a case.
    connected: tuple[str, ...] = ()
    # True for "<type>/<n>/<year>/(Filing No.)" entries -- listed by
    # filing number because the matter isn't registered yet.
    is_filing_number: bool = False

    @property
    def normalized_key(self) -> tuple[str, str, str] | None:
        return normalize_case_token(self.case_token)


@dataclass
class CauseList:
    """One cause-list document: one court hall, one date."""

    court_hall: str = ""
    list_date: date | None = None
    list_type: str = ""
    judges: tuple[str, ...] = ()
    items: list[CauseListItem] = field(default_factory=list)

    def index_by_case(self) -> dict[tuple[str, str, str], CauseListItem]:
        """Normalized (TYPE, NUMBER, YEAR) -> item, for case matching.

        Filing-number entries are EXCLUDED. A filing number and a
        registration number are independent series which collide freely
        ("WA/36270/2026 (Filing No.)" is a different matter from a
        registered WA/36270/2026), and tracked cases carry registration
        numbers -- indexing both would eventually stamp another matter's
        item number onto a real hearing.

        On a duplicate token the FIRST occurrence wins: the earlier item
        number is the one the advocate is called on.
        """
        index: dict[tuple[str, str, str], CauseListItem] = {}
        for item in self.items:
            if item.is_filing_number:
                continue
            key = item.normalized_key
            if key is not None and key not in index:
                index[key] = item
        return index


def normalize_case_token(token: str) -> tuple[str, str, str] | None:
    """'W.A./102/2026' -> ('WA', '102', '2026'); None if unparseable.

    Normalisation exists because the same case is written differently on
    either side of the match: the cause list prints "WA/102/2026" while a
    tracked Case's case_number may carry punctuation, spacing or an "of"
    from whichever eCourts response created it. Dots/spaces are stripped
    from the type and leading zeros from the number so "W.A./0102/2026"
    and "WA/102/2026" are the same case.

    Returns None (never raises) for anything that isn't a case token --
    the caller treats that as "no identity to match on", which is a
    normal outcome for a CNR-numbered case.
    """
    if not token:
        return None

    token = _FILING_NUMBER_SUFFIX_RE.sub("", str(token))
    match = _CASE_TOKEN_RE.match(token)
    if match is None:
        return None

    case_type = re.sub(r"[.\s]", "", match.group(1)).upper()
    if not case_type:
        return None
    serial = match.group(2).lstrip("0") or "0"
    return case_type, serial, match.group(3)


def parse_cause_list_html(html: str) -> CauseList:
    """Parse one TS High Court cause-list document.

    Raises CauseListParseError if this isn't that document -- a silent
    empty result would look exactly like "none of your cases are listed
    today", which is the one wrong answer this feature must not give.
    """
    soup = BeautifulSoup(html or "", "lxml")

    table = soup.find("table", id="dataTable")
    if table is None:
        raise CauseListParseError(
            "No table#dataTable in the document -- this does not look like a "
            "Telangana High Court cause list (the portal layout may have changed)."
        )

    header_text = _collapse(table.get_text(" ", strip=True)[:2000])

    cause_list = CauseList(
        court_hall=_extract_court_hall(header_text),
        list_date=_extract_list_date(header_text),
        list_type=_extract_list_type(header_text),
        judges=_extract_judges(table),
    )

    for tbody in table.find_all("tbody"):
        item = _parse_item(tbody)
        if item is not None:
            cause_list.items.append(item)

    if not cause_list.items:
        raise CauseListParseError(
            "table#dataTable contained no parseable items -- treating as a "
            "layout change rather than an empty list, since a published "
            "cause list always has at least one matter."
        )

    logger.info(
        "Parsed %s cause list: court hall %s, %s, %d items.",
        COURT_LABEL,
        cause_list.court_hall or "?",
        cause_list.list_date.isoformat() if cause_list.list_date else "undated",
        len(cause_list.items),
    )
    return cause_list


def _parse_item(tbody) -> CauseListItem | None:
    """One <tbody> -> one item, or None when it holds no matter (the
    stage-header-only blocks)."""
    link = tbody.find("a", id="caseNumber")
    if link is None:
        return None

    token = (link.get("data-case-id") or link.get_text(" ", strip=True) or "").strip()
    if not token:
        return None

    row = link.find_parent("tr")
    if row is None:
        return None
    cells = row.find_all("td", recursive=False)
    if len(cells) < 2:
        return None

    item_number = _collapse(cells[0].get_text(" ", strip=True))
    parties = _collapse(cells[2].get_text(" ", strip=True)) if len(cells) > 2 else ""

    stage_span = tbody.find("span", class_="stage-name")
    stage = _collapse(stage_span.get_text(" ", strip=True)) if stage_span else ""

    connected = tuple(
        value
        for div in cells[1].find_all("div")
        if (value := (div.get("data-case-id") or "").strip())
    )

    parsed = normalize_case_token(token)
    return CauseListItem(
        item_number=item_number,
        case_token=token,
        case_type=parsed[0] if parsed else "",
        case_serial=parsed[1] if parsed else "",
        case_year=parsed[2] if parsed else "",
        stage=stage,
        parties=parties,
        connected=connected,
        is_filing_number=bool(_FILING_NUMBER_SUFFIX_RE.search(token)),
    )


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _extract_court_hall(text: str) -> str:
    match = _COURT_HALL_RE.search(text)
    return match.group(1) if match else ""


def _extract_list_date(text: str) -> date | None:
    match = _LIST_DATE_RE.search(text)
    if match is None:
        return None
    day, month_name, year = match.groups()
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(f"{int(day)} {month_name} {year}", fmt).date()
        except ValueError:
            continue
    logger.warning("Could not parse cause-list date from %r", match.group(0))
    return None


def _extract_list_type(text: str) -> str:
    match = _LIST_TYPE_RE.search(text)
    return match.group(1).upper() if match else ""


def _extract_judges(table) -> tuple[str, ...]:
    """Judge names from the list header ("THE HONOURABLE ...")."""
    judges = []
    for node in table.find_all(string=re.compile(r"HON'?BLE|HONOURABLE", re.IGNORECASE)):
        name = _collapse(str(node))
        if name and name not in judges:
            judges.append(name)
    return tuple(judges)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def build_cause_list_url(target_date: date) -> str:
    """The URL for this court's cause list on `target_date`.

    Read from settings.TELANGANA_HC_CAUSE_LIST_URL, a template taking
    {date} (ISO), {dd}, {mm}, {yyyy}. There is no hardcoded default: the
    saved sample this parser was built from carries no URL of its own
    (its #globalUrl is blank), so guessing one would produce a job that
    silently fetches the wrong page rather than failing loudly.
    """
    from django.conf import settings

    template = getattr(settings, "TELANGANA_HC_CAUSE_LIST_URL", "") or ""
    if not template:
        raise CauseListNotConfiguredError(
            "TELANGANA_HC_CAUSE_LIST_URL is not set. Set it in the environment "
            "to the court's cause-list URL template, using {date} (ISO), {dd}, "
            "{mm} and/or {yyyy} as placeholders, e.g. "
            "'https://<host>/causelist?date={dd}-{mm}-{yyyy}'."
        )

    return template.format(
        date=target_date.isoformat(),
        dd=f"{target_date.day:02d}",
        mm=f"{target_date.month:02d}",
        yyyy=str(target_date.year),
    )


def fetch_cause_list(target_date: date, *, timeout: int = 30) -> CauseList:
    """Download and parse this court's cause list for `target_date`.

    A plain requests call, not the eCourts provider machinery: that
    machinery exists for CAPTCHA-gated case lookups on
    services/hcservices.ecourts.gov.in and has no cause-list endpoint at
    all. The TS High Court publishes its lists on its own portal, which
    needs no session or CAPTCHA -- so the only thing worth carrying over
    is the timeout/user-agent hygiene, done here.

    Raises CauseListNotPublishedError on a 404 (the ordinary "list isn't
    up yet" answer), CauseListNotConfiguredError when the URL is unset,
    and CauseListParseError when what comes back isn't a cause list.
    """
    import requests

    from .exceptions import CauseListNotPublishedError

    url = build_cause_list_url(target_date)
    logger.info("Fetching %s cause list for %s: %s", COURT_LABEL, target_date, url)

    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "CaseIntel/1.0 (cause-list fetcher)"},
        )
    except requests.RequestException as exc:
        raise CauseListNotPublishedError(
            f"Could not reach the cause-list portal for {target_date}: {exc}"
        ) from exc

    if response.status_code == 404:
        raise CauseListNotPublishedError(
            f"No cause list published for {target_date} yet (HTTP 404)."
        )
    if response.status_code >= 400:
        raise CauseListNotPublishedError(
            f"Cause-list portal returned HTTP {response.status_code} for {target_date}."
        )

    return parse_cause_list_html(response.text)
