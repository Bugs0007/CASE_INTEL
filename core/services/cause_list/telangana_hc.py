"""Fetcher + parser for the High Court for the State of Telangana cause
lists, served through eCourts' hcservices portal.

VERIFIED LIVE 3 Aug 2026 -- the fixtures under
core/tests/fixtures/causelists/live_2026-08-03/ are the real artifacts of
that run (meta-table HTML, one PDF per list type, row inventory).

The real flow, which is NOT a plain GET of an HTML page:

    POST /hcservices/cases_qry/index_qry.php
        action_code=showCauseList  flag=civ_t  selprevdays=0
        captcha=<solved>  state_code=29  court_code=1
        caseStatusSearchType=CLcauselist  causelist_date=DD-MM-YYYY
      -> HTML META-TABLE (table.causelistTbl):
             Sr No | Bench | Cause List Type | View Causelist
         58 rows for a normal working day, one per judge-bench per list
         type. The "benches" are JUDGE COMBINATIONS, not seats: Telangana
         has exactly one bench ("1", Principal Bench at Hyderabad), which
         is why one submit covers the whole court.
      -> each row links to cases/display_causelist_pdf.php?filename=<token>
      -> that PDF is the actual cause list. Text-based, no OCR needed.

Three portal/library quirks this module exists to absorb:

  1. bharat_courts' own parse_cause_list() builds the PDF URL as
     "<base>/cases_qry/<href>" while the href already begins with
     "cases/", producing .../cases_qry/cases/... which 404s. build_pdf_url()
     below is the corrected join -- verified 200/application/pdf.
  2. The PDFs are served with a UTF-8 BOM in front of "%PDF", which makes
     strict parsers reject them. strip_pdf_bom() cuts to the real header.
  3. flag=cri_t returns ZERO rows; civ_t alone returns everything,
     including BAIL PETITIONS. Only civ_t is ever sent.

Parsing is COORDINATE-BASED, not text-order-based. pdfminer's plain
extract_text() walks these documents column-block-wise, so S.No. gets
separated from the case number it belongs to (item 2's number lands
several lines away from "CC/3550/2026"). Rows are instead rebuilt by
pairing the item column with the case column at the same vertical
position. Column x-offsets are DETECTED PER DOCUMENT rather than
hardcoded: the real lists use at least three different layouts
(item column at 44.6 / 44.8 / 45.0, case column at 68.0 / 69.2 / 71.0),
so a fixed offset silently parses some list types as empty -- which
reads exactly like "none of your cases are listed", the one wrong answer
this feature must never give.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from bs4 import BeautifulSoup
from django.conf import settings
from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTTextContainer

from .exceptions import (
    CauseListNotConfiguredError,
    CauseListNotPublishedError,
    CauseListParseError,
)

logger = logging.getLogger(__name__)

COURT_KEY = "telangana_hc"
COURT_LABEL = "High Court for the State of Telangana"

# bharat_courts' court-registry key and the bench dropdown value. Both are
# settings-overridable but have working defaults -- unlike the old
# TELANGANA_HC_CAUSE_LIST_URL, this flow needs no operator-supplied URL at
# all, because the endpoint is a fixed POST target in the library.
DEFAULT_COURT_REGISTRY_KEY = "telangana"
DEFAULT_BENCH_CODE = "1"

# Only civil. Verified live: cri_t returns zero rows and civ_t already
# includes the criminal lists (BAIL PETITIONS, CRLP matters).
CAUSE_LIST_FLAG = "civ_t"

_COURT_HALL_RE = re.compile(r"COURT\s*NO\.?\s*([0-9]+)", re.IGNORECASE)
_LIST_DATE_RE = re.compile(
    r"To\s+be\s+heard\s+on\s+\w+\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+([A-Za-z]+)\s+(\d{4})",
    re.IGNORECASE,
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

# "wt4 WP/21946/2024" -- a matter tagged to ("with") item 4, printed in
# the item column with its case number inline instead of in the case
# column. Real and common: the ADJOURNED MOTION LIST fixture has item
# numbers 1,2,3,7,8..., with 4/5/6 present only in this form.
_TAGGED_ITEM_RE = re.compile(r"^(wt\s*\d+[a-z]?)\s+(.+)$", re.IGNORECASE | re.DOTALL)

_PLAIN_ITEM_RE = re.compile(r"^\d{1,4}$")

# Repeated on every continuation page inside the case column; not a case.
_PAGE_HEADER_MARKERS = ("CAUSELIST COURT NO", "HIGH COURT,HYDERABAD", "HIGH COURT, HYDERABAD")
_TABLE_HEADER_MARKERS = ("S.NO.", "CASE NUMBER", "PARTY DETAILS")

# Vertical tolerance when pairing an item number with its case number.
# Both are drawn on the same baseline, so this only absorbs rounding.
_ROW_Y_TOLERANCE = 3.0
# Horizontal tolerance when assigning a block to a detected column.
_COLUMN_X_TOLERANCE = 4.0


# ---------------------------------------------------------------------------
# Portal quirks (the two library/portal bugs this module corrects)
# ---------------------------------------------------------------------------


def strip_pdf_bom(data: bytes) -> bytes:
    """Cut a portal PDF down to its real "%PDF" header.

    hcservices prefixes cause-list PDFs with a UTF-8 BOM
    (b"\\xef\\xbb\\xbf%PDF-1.4"), which strict parsers reject outright.
    Returns the input unchanged when there is no preamble.
    """
    if not data:
        return data
    start = data.find(b"%PDF")
    if start <= 0:
        return data
    return data[start:]


def build_pdf_url(href: str, *, base_url: str | None = None) -> str:
    """Absolute URL for a "View Causelist" link.

    Corrects bharat_courts.hcservices.parser.parse_cause_list, which joins
    these as "<base>/cases_qry/<href>" even though href already starts
    with "cases/" -- the resulting .../cases_qry/cases/display_causelist_pdf.php
    is a hard 404. Verified live: the form below returns 200 with
    content-type application/pdf.
    """
    from bharat_courts.hcservices import endpoints

    base = (base_url or endpoints.BASE_URL).rstrip("/")
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"{base}/{href.lstrip('/')}"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CauseListEntry:
    """One row of the meta-table: a PDF that exists for this date."""

    serial: str
    bench: str
    list_type: str
    href: str

    @property
    def pdf_url(self) -> str:
        return build_pdf_url(self.href)


@dataclass(frozen=True)
class CauseListItem:
    """One listed matter.

    Carries its own court hall / bench / list type because a single date
    spans ~58 separate documents across different halls -- unlike the
    earlier one-document-per-day assumption, the hall is a property of the
    item, not of the day.
    """

    item_number: str
    case_token: str
    stage: str = ""
    court_hall: str = ""
    bench: str = ""
    list_type: str = ""
    # Connected IA/interlocutory entries printed under the main case. Kept
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
class CauseListDocument:
    """One cause-list PDF: one court hall, one bench, one list type."""

    court_hall: str = ""
    bench: str = ""
    list_type: str = ""
    list_date: date | None = None
    items: list[CauseListItem] = field(default_factory=list)


@dataclass
class CauseListDay:
    """Every cause-list document published for one date."""

    list_date: date | None = None
    documents: list[CauseListDocument] = field(default_factory=list)

    @property
    def items(self) -> list[CauseListItem]:
        return [item for doc in self.documents for item in doc.items]

    def index_by_case(self) -> dict[tuple[str, str, str], CauseListItem]:
        """Normalized (TYPE, NUMBER, YEAR) -> item, across every document.

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


# ---------------------------------------------------------------------------
# Meta-table parsing
# ---------------------------------------------------------------------------


def parse_meta_table(html: str) -> list[CauseListEntry]:
    """Parse the showCauseList response into one entry per PDF.

    Returns [] when the portal has published nothing for the date -- the
    caller turns that into CauseListNotPublishedError. Raises
    CauseListParseError only when the response is present but is not this
    table at all, which means the portal changed and every case would
    otherwise silently read as "not listed".
    """
    text = (html or "").strip().lstrip("﻿").strip()
    if not text:
        raise CauseListParseError("Empty response from the cause-list endpoint.")

    soup = BeautifulSoup(text, "lxml")
    table = soup.find("table", class_="causelistTbl") or soup.find("table")
    if table is None:
        # No table at all is how the portal reports "nothing for this
        # date" -- but only if the response is also short. A long
        # table-less response is a layout change worth failing on.
        if len(text) < 2000:
            return []
        raise CauseListParseError(
            "Cause-list response contains no table -- the hcservices layout "
            "may have changed."
        )

    entries: list[CauseListEntry] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue  # header row
        link = cells[3].find("a", href=True)
        if link is None:
            continue
        entries.append(
            CauseListEntry(
                serial=cells[0].get_text(strip=True),
                bench=_collapse(cells[1].get_text()),
                list_type=_collapse(cells[2].get_text()),
                href=link["href"].strip(),
            )
        )
    return entries


# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Block:
    """One laid-out text container, with the geometry we need."""

    page: int
    x0: float
    y1: float
    text: str


def _read_blocks(data: bytes) -> list[_Block]:
    blocks: list[_Block] = []
    try:
        pages = extract_pages(io.BytesIO(data), laparams=LAParams())
        for page_no, page in enumerate(pages):
            for element in page:
                if not isinstance(element, LTTextContainer):
                    continue
                text = element.get_text().strip()
                if text:
                    blocks.append(
                        _Block(page=page_no, x0=element.x0, y1=element.y1, text=text)
                    )
    except Exception as exc:  # noqa: BLE001 -- pdfminer raises many types
        raise CauseListParseError(f"Could not read the cause-list PDF: {exc}") from exc
    return blocks


def _detect_columns(blocks: list[_Block]) -> tuple[float, float]:
    """Find the (item column, case column) x-offsets for THIS document.

    Detected rather than hardcoded because the real lists ship at least
    three layouts (item at 44.6/44.8/45.0, case at 68.0/69.2/71.0). A
    hardcoded offset parses the other layouts as zero items, which is
    indistinguishable from "your case isn't listed".

    The item column is the cluster holding the most item-shaped tokens
    (a bare number, or "wt4 ...").

    The case column is then chosen by ROW EVIDENCE -- the cluster to its
    right whose blocks most often share a baseline with an item number --
    rather than simply "the next cluster to the right". The naive rule
    picks up the centred page header repeated on every continuation page
    ("MOTION LIST CAUSELIST COURT NO 4-FOR MONDAY..."), whose x0 lands
    between the two real columns and varies with the title's width. That
    mis-detection cost three of the eight list types their entire
    contents.
    """
    clusters: list[list[_Block]] = []
    for block in sorted(blocks, key=lambda b: b.x0):
        if clusters and abs(block.x0 - clusters[-1][0].x0) <= _COLUMN_X_TOLERANCE:
            clusters[-1].append(block)
        else:
            clusters.append([block])

    if not clusters:
        raise CauseListParseError("Cause-list PDF contains no text.")

    def item_score(cluster: list[_Block]) -> int:
        return sum(
            1
            for b in cluster
            if _PLAIN_ITEM_RE.match(b.text) or _TAGGED_ITEM_RE.match(b.text)
        )

    best = max(clusters, key=item_score)
    if item_score(best) == 0:
        raise CauseListParseError(
            "No item-number column found in the cause-list PDF -- the layout "
            "may have changed."
        )

    item_x = min(b.x0 for b in best)
    item_rows = {
        (b.page, round(b.y1, 1))
        for b in best
        if _PLAIN_ITEM_RE.match(b.text)
    }

    def row_overlap(cluster: list[_Block]) -> int:
        hits = 0
        for b in cluster:
            if _is_noise(b.text):
                continue
            if any(
                page == b.page and abs(y - b.y1) <= _ROW_Y_TOLERANCE
                for page, y in item_rows
            ):
                hits += 1
        return hits

    candidates = [
        c for c in clusters if min(b.x0 for b in c) > item_x + _COLUMN_X_TOLERANCE
    ]
    if not candidates:
        raise CauseListParseError("No case-number column found in the cause-list PDF.")

    # Ties break leftward: the case number is the first column after S.No.
    best_case = max(
        candidates, key=lambda c: (row_overlap(c), -min(b.x0 for b in c))
    )
    if row_overlap(best_case) == 0:
        raise CauseListParseError(
            "No column pairs with the item numbers in the cause-list PDF -- "
            "the layout may have changed."
        )
    return item_x, min(b.x0 for b in best_case)


def _is_noise(text: str) -> bool:
    upper = text.upper()
    if any(marker in upper for marker in _PAGE_HEADER_MARKERS):
        return True
    return any(upper.startswith(marker) for marker in _TABLE_HEADER_MARKERS)


def _split_case_block(text: str) -> tuple[str, tuple[str, ...]]:
    """First line is the case number; the rest are connected IA entries."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return "", ()
    return lines[0], tuple(lines[1:])


def parse_cause_list_pdf(
    data: bytes, *, bench: str = "", list_type: str = ""
) -> CauseListDocument:
    """Parse one cause-list PDF into its listed matters.

    `bench` and `list_type` come from the meta-table row that linked to
    this PDF and are treated as authoritative -- the PDF's own header
    spells them inconsistently ("DAILY LIST-1" vs "DAILY LIST -2").

    Raises CauseListParseError rather than returning an empty document
    when the file isn't parseable as this court's list.
    """
    blocks = _read_blocks(strip_pdf_bom(data))
    if not blocks:
        raise CauseListParseError("Cause-list PDF contains no extractable text.")

    full_text = "\n".join(b.text for b in blocks)
    document = CauseListDocument(
        court_hall=_extract_court_hall(full_text),
        bench=bench,
        list_type=list_type or _extract_list_type(full_text),
        list_date=_extract_list_date(full_text),
    )

    item_x, case_x = _detect_columns(blocks)

    item_blocks = [b for b in blocks if abs(b.x0 - item_x) <= _COLUMN_X_TOLERANCE]
    case_blocks = [b for b in blocks if abs(b.x0 - case_x) <= _COLUMN_X_TOLERANCE]

    # Reading order: page, then down the page.
    item_blocks.sort(key=lambda b: (b.page, -b.y1))

    stage = ""
    for block in item_blocks:
        text = block.text.strip()
        if _is_noise(text):
            continue

        tagged = _TAGGED_ITEM_RE.match(text)
        if tagged:
            # "wt4 WP/21946/2024\nIA 1/2024 ..." -- number and case are in
            # the SAME block, so no row pairing is needed.
            number = re.sub(r"\s+", "", tagged.group(1))
            case_token, connected = _split_case_block(tagged.group(2))
            _append(document, number, case_token, connected, stage)
            continue

        if not _PLAIN_ITEM_RE.match(text):
            # Anything else in this column is a section heading
            # ("FOR ADMISSION", "ANTICIPATORY BAIL PETITIONS"), which
            # applies to the items that follow it.
            stage = _collapse(text)
            continue

        partner = _case_block_at(case_blocks, block)
        if partner is None:
            logger.debug(
                "Cause list: item %s on page %d has no case number beside it.",
                text,
                block.page,
            )
            continue
        case_token, connected = _split_case_block(partner.text)
        _append(document, text, case_token, connected, stage)

    if not document.items:
        raise CauseListParseError(
            "No listed matters found in the cause-list PDF -- refusing to "
            "report an empty list, which is indistinguishable from 'your "
            "case is not listed'."
        )

    logger.debug(
        "Parsed cause list: hall %s, bench %r, %s, %d items.",
        document.court_hall or "?",
        document.bench,
        document.list_type or "?",
        len(document.items),
    )
    return document


def _case_block_at(case_blocks: list[_Block], item: _Block) -> _Block | None:
    """The case-number block drawn on the same baseline as `item`."""
    for candidate in case_blocks:
        if candidate.page != item.page:
            continue
        if abs(candidate.y1 - item.y1) <= _ROW_Y_TOLERANCE and not _is_noise(
            candidate.text
        ):
            return candidate
    return None


def _append(
    document: CauseListDocument,
    number: str,
    case_token: str,
    connected: tuple[str, ...],
    stage: str,
) -> None:
    if not case_token:
        return
    document.items.append(
        CauseListItem(
            item_number=number,
            case_token=case_token,
            stage=stage,
            court_hall=document.court_hall,
            bench=document.bench,
            list_type=document.list_type,
            connected=connected,
            is_filing_number=bool(_FILING_NUMBER_SUFFIX_RE.search(case_token)),
        )
    )


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _extract_court_hall(text: str) -> str:
    match = _COURT_HALL_RE.search(text or "")
    return match.group(1) if match else ""


def _extract_list_date(text: str) -> date | None:
    match = _LIST_DATE_RE.search(text or "")
    if match is None:
        return None
    day, month_name, year = match.groups()
    for fmt in ("%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(f"{day} {month_name} {year}", fmt).date()
        except ValueError:
            continue
    return None


def _extract_list_type(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip().strip("()").strip()
        if stripped.upper().endswith("LIST") and 3 < len(stripped) < 60:
            return _collapse(stripped)
    return ""


# ---------------------------------------------------------------------------
# Fetching (reuses HCServicesClient's CAPTCHA machinery)
# ---------------------------------------------------------------------------


def _court():
    """The bharat_courts Court record for Telangana HC."""
    from bharat_courts import get_court

    key = getattr(settings, "TELANGANA_HC_COURT_KEY", DEFAULT_COURT_REGISTRY_KEY)
    try:
        court = get_court(key)
    except Exception as exc:  # noqa: BLE001 -- registry raises its own types
        raise CauseListNotConfiguredError(
            f"Unknown court registry key {key!r} (settings.TELANGANA_HC_COURT_KEY): {exc}"
        ) from exc
    if court is None:
        raise CauseListNotConfiguredError(
            f"Unknown court registry key {key!r} (settings.TELANGANA_HC_COURT_KEY). "
            f"Expected something like {DEFAULT_COURT_REGISTRY_KEY!r}."
        )
    return court


def fetch_cause_list_day(target_date: date) -> CauseListDay:
    """Fetch every cause-list document published for `target_date`.

    One CAPTCHA-gated submit, then one download per meta-table row (~58
    on a normal working day). Raises CauseListNotPublishedError when the
    court hasn't put the date up yet, which is the ordinary state the
    evening before a hearing.
    """
    return asyncio.run(_fetch_cause_list_day(target_date))


async def _fetch_cause_list_day(target_date: date) -> CauseListDay:
    from bharat_courts import HCServicesClient
    from bharat_courts.hcservices import endpoints

    court = _court()
    bench_code = getattr(settings, "TELANGANA_HC_BENCH_CODE", DEFAULT_BENCH_CODE)
    causelist_date = target_date.strftime("%d-%m-%Y")
    # The portal needs to be told explicitly when a date is in the past.
    selprevdays = "1" if target_date < date.today() else "0"

    def build_form(captcha: str) -> dict:
        return endpoints.cause_list_form(
            state_code=court.state_code,
            court_code=bench_code,
            captcha=captcha,
            causelist_date=causelist_date,
            flag=CAUSE_LIST_FLAG,
            selprevdays=selprevdays,
        )

    async with HCServicesClient() as client:
        # _post_with_captcha_retry is bharat_courts' own solve-and-retry
        # loop (OCR against securimage_show.php). Reused deliberately --
        # core/services/court_data/ecourts_provider.py already drives the
        # same private helper for CNR search and order downloads, so this
        # adds no new scraping machinery.
        response = await client._post_with_captcha_retry(
            endpoints.INDEX_QRY_URL, build_form
        )
        entries = parse_meta_table(response.text)
        if not entries:
            raise CauseListNotPublishedError(
                f"hcservices lists no cause-list documents for {target_date}."
            )

        logger.info(
            "Cause list %s: %d document(s) published for %s.",
            COURT_KEY,
            len(entries),
            target_date,
        )

        documents: list[CauseListDocument] = []
        for entry in entries:
            try:
                pdf_response = await client._http.get(entry.pdf_url)
                document = parse_cause_list_pdf(
                    pdf_response.content, bench=entry.bench, list_type=entry.list_type
                )
            except Exception as exc:  # noqa: BLE001
                # One unreadable document must not lose the other 57. A
                # case is only reported "not listed" when it appears in NO
                # document, so a partial day is still far better than no
                # day -- but the gap is logged loudly.
                logger.warning(
                    "Cause list %s: could not read '%s / %s' (%s) -- skipping it.",
                    COURT_KEY,
                    entry.bench,
                    entry.list_type,
                    exc,
                )
                continue
            documents.append(document)

    if not documents:
        raise CauseListParseError(
            f"All {len(entries)} cause-list documents for {target_date} failed to "
            f"parse -- refusing to report every case as 'not listed'."
        )

    list_date = next((d.list_date for d in documents if d.list_date), None)
    return CauseListDay(list_date=list_date, documents=documents)
