"""Supreme Court of India daily cause lists (sci.gov.in). DORMANT.

Built and tested against real files, never routed to: a Supreme Court case
cannot exist in the database (`Case.court_type` is district / high_court,
and an `ESCR` CNR is looked up on both portals and rejected as not found),
so `resolve` always says "not covered". The day Supreme Court tracking
exists, flipping `dormant` and writing `resolve` is all that is left.

What the portal gives (verified live 2026-10-10):
  * no CAPTCHA for published lists;
  * `https://www.sci.gov.in/cause-list/` has an HTML table whose cells link
    the PDFs -- file names are READ from it, never constructed:
        /jonew/cl/<YYYY-MM-DD>/{M_J_1,M_J_2,M_C_1,M_C_2,M_S_1,M_S_2,M_R_1,F_J_1,M_CC_1}.pdf
        /jonew/cl/advance/<YYYY-MM-DD>/M_J.pdf     /jonew/cl/wk/<from>_<to>/weekly.pdf
  * the PDF URL works with no cookie, so it can be shown to a user;
  * HTTP `Last-Modified` is the publish time.
"""

from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path

from ..base import (
    PORTAL_SCI,
    CauseListAdapter,
    CauseListEntry,
    FetchResult,
    ListingTarget,
    ParsedDoc,
    RawDoc,
    Resolution,
)
from ..exceptions import CauseListFetchError, CauseListParseError
from .layouts.pdftext import ROW_TOLERANCE, Line, find_court_hall, find_list_date, read_lines

logger = logging.getLogger(__name__)

KEY = "supreme_court"
INDEX_URL = "https://www.sci.gov.in/cause-list/"
_DAILY_LINK = re.compile(
    r'href="(https://api\.sci\.gov\.in/jonew/cl/(?P<date>\d{4}-\d{2}-\d{2})/(?P<stem>[A-Za-z0-9_]+)\.pdf)"'
)


@dataclass(frozen=True)
class IndexLink:
    url: str
    stem: str  # M_J_1 ...
    list_date: date


def parse_index(html: str, list_date: date | None = None) -> list[IndexLink]:
    """Daily-list links on the portal's index page (advance and weekly lists
    are different documents and are ignored)."""
    links: list[IndexLink] = []
    seen = set()
    for match in _DAILY_LINK.finditer(html or ""):
        day = datetime.strptime(match.group("date"), "%Y-%m-%d").date()
        if list_date is not None and day != list_date:
            continue
        if match.group(1) in seen:
            continue
        seen.add(match.group(1))
        links.append(IndexLink(match.group(1), match.group("stem"), day))
    return links


# --- PDF -----------------------------------------------------------------

_ITEM = re.compile(r"^(?P<item>[1-9]\d{0,3})(?:\s+(?P<rest>\S.*))?$")
_FULL_CASE = re.compile(
    r"^(?P<type>[A-Za-z][A-Za-z.()&/\s]{0,28}?)\s*No\.?\s*(?P<first>\d{1,6})(?:\s*[-–]\s*(?P<last>\d{1,6}))?\s*/\s*(?P<year>\d{4})"
)
_TYPE_ONLY = re.compile(r"^(?P<type>[A-Za-z][A-Za-z.()&/\s]{0,28}?)\s*No\.?\s*$")
_NUMBER_LINE = re.compile(r"^(?P<first>\d{1,6})(?:\s*[-–]\s*(?P<last>\d{1,6}))?\s*/\s*(?P<year>\d{4})")
_DIARY = re.compile(r"^Diary\s*No\.?\s*(\d{1,8})\s*[-/]\s*(\d{4})", re.IGNORECASE)
_RANGE_CAP = 300


def _expand(case_type: str, first: str, last: str | None, year: str) -> list[str]:
    case_type = re.sub(r"\s+", "", case_type).strip(".")
    a = int(first)
    b = int(last) if last else a
    if b < a or b - a >= _RANGE_CAP:
        b = a
    return [f"{case_type}/{n}/{year}" for n in range(a, b + 1)]


def parse_sc_pdf(path: Path, *, list_type: str = "") -> ParsedDoc:
    """One Supreme Court daily list -> entries. Item numbers at the left,
    `C.A. No. 5981/2023` beside them (a range `No. 8264-8292/2023` wraps its
    number onto the next line and expands to one entry per case)."""
    lines, width = read_lines(path)
    items = sorted(
        (
            ln for ln in lines
            if ln.x0 < width * 0.12 and (m := _ITEM.match(ln.text)) is not None
            and (m.group("rest") is None or _FULL_CASE.match(m.group("rest")) or _TYPE_ONLY.match(m.group("rest"))
                 or _DIARY.match(m.group("rest")))
        ),
        key=lambda l: (l.page, -round(l.y1)),
    )
    if not items:
        raise CauseListParseError("No item-number column found in the Supreme Court list.")
    item_x = min(i.x0 for i in items)
    items = [i for i in items if abs(i.x0 - item_x) <= 6]

    header = " ".join(ln.text for ln in lines if ln.page == 0 and ln.y1 > items[0].y1)
    list_date = find_list_date(header)
    entries: list[CauseListEntry] = []
    unpaired = 0
    unpaired_detail: list[tuple[str, str]] = []
    for index, item in enumerate(items):
        item_match = _ITEM.match(item.text)
        number = item_match.group("item")
        if item_match.group("rest"):
            first_line, text = item, re.sub(r"\s+", " ", item_match.group("rest"))
        else:
            mates = sorted(
                (
                    ln for ln in lines
                    if ln.page == item.page and abs(ln.y1 - item.y1) <= ROW_TOLERANCE and ln.x0 > item.x1
                ),
                key=lambda l: l.x0,
            )
            if not mates:
                unpaired += 1
                continue
            first_line = mates[0]
            text = re.sub(r"\s+", " ", first_line.text)
        match = _FULL_CASE.match(text)
        tokens: list[str] = []
        if match:
            tokens = _expand(match.group("type"), match.group("first"), match.group("last"), match.group("year"))
        elif _TYPE_ONLY.match(text):
            below = [
                ln for ln in lines
                if ln.page == item.page and abs(ln.x0 - first_line.x0) <= 6
                and 0 < item.y1 - ln.y1 <= 40 and ln.y1 < first_line.y1 - 1
            ]
            below.sort(key=lambda l: -l.y1)
            num_match = _NUMBER_LINE.match(below[0].text) if below else None
            if num_match:
                tokens = _expand(
                    _TYPE_ONLY.match(text).group("type"), num_match.group("first"),
                    num_match.group("last"), num_match.group("year"),
                )
        diary = _DIARY.match(text)
        if diary and not tokens:
            # A matter listed by DIARY number (not yet registered): kept so
            # the item is accounted for, never matchable (like a filing no.).
            entries.append(
                CauseListEntry(
                    item_number=number, case_token=f"Diary No. {diary.group(1)}/{diary.group(2)}",
                    list_type=list_type, court_hall=find_court_hall(header), is_filing_number=True,
                )
            )
            continue
        if not tokens:
            unpaired += 1
            unpaired_detail.append((item.text, text[:40]))
            continue
        for token in tokens:
            entries.append(
                CauseListEntry(
                    item_number=number, case_token=token, list_type=list_type,
                    court_hall=find_court_hall(header),
                )
            )
    if not entries:
        raise CauseListParseError("Item numbers found but no Supreme Court case numbers beside them.")
    if unpaired / len(items) > 0.10:
        raise CauseListParseError(
            f"{unpaired} of {len(items)} Supreme Court items have no readable case number: {unpaired_detail[:5]}"
        )
    return ParsedDoc(entries=entries, list_date=list_date)


# --- adapter ---------------------------------------------------------------


class SupremeCourtAdapter(CauseListAdapter):
    key = KEY
    display_name = "Supreme Court of India"
    portal = PORTAL_SCI
    dormant = True

    def resolve(self, case) -> Resolution:
        return Resolution.unsupported("Supreme Court cases are not tracked yet", KEY)

    def target_from_key(self, key: str) -> ListingTarget:
        return ListingTarget(adapter=KEY, key="daily", label="Supreme Court daily lists", params={})

    def coverage_url(self, case) -> str:
        return INDEX_URL

    def fetch(self, target: ListingTarget, list_date: date, workdir: Path) -> FetchResult:
        try:
            return fetchlib_run(self._fetch(list_date, workdir))
        except CauseListFetchError as exc:
            return FetchResult(status="fetch_error", error=str(exc))
        except Exception as exc:  # noqa: BLE001
            return FetchResult(status="fetch_error", error=f"{type(exc).__name__}: {exc}"[:300])

    async def _fetch(self, list_date: date, workdir: Path) -> FetchResult:
        from bharat_courts.http import RateLimitedClient

        from ..fetchlib import Pacer, download_pdf

        pacer = Pacer()
        async with RateLimitedClient() as http:
            await pacer.wait()
            page = await http.get(INDEX_URL, headers={"Referer": INDEX_URL})
            links = parse_index(page.text, list_date)
            if not links:
                return FetchResult(status="none_available", note="no daily list for this date on the index")
            docs: list[RawDoc] = []
            for n, link in enumerate(links):
                dest = workdir / f"{n:02d}_{link.stem}.pdf"
                doc = RawDoc(
                    doc_key=link.stem, status="fetch_error", list_type=link.stem, bench_label="Supreme Court",
                    source_ref=link.url, source_public=True,
                )
                try:
                    got = await download_pdf(http, link.url, dest, pacer=pacer)
                except CauseListFetchError as exc:
                    doc.error = str(exc)
                else:
                    if got.kind == "pdf":
                        doc.status, doc.path, doc.sha256, doc.size = "ok", dest, got.sha256, got.size
                    elif got.kind == "not_uploaded":
                        doc.status = "not_uploaded"
                    else:
                        doc.error = f"unexpected body: {got.preview[:60]!r}"
                docs.append(doc)
        return FetchResult(status="ok", docs=docs, doc_total=len(links))

    def parse(self, doc: RawDoc) -> ParsedDoc:
        return parse_sc_pdf(Path(doc.path), list_type=doc.list_type)


def fetchlib_run(coro):
    from ..fetchlib import run_bounded, setting

    return run_bounded(coro, float(setting("CAUSE_LIST_SCI_BUDGET_SECONDS", 600)))


_ADAPTER = None


def get_adapter() -> SupremeCourtAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = SupremeCourtAdapter()
    return _ADAPTER
