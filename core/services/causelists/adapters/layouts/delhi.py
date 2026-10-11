"""Delhi High Court (hcservices): one PDF per court number, case numbers
hard-wrapped inside a narrow column.

    ITEM NO. | CASE NO.            | CASE TITLE | ADVOCATE | CASE STAGE | REMARKS
    1        | W.P.(C)-            |
             | 8569//2026          |
             | CM APPL.            |
             | 40178/2026          |
    2        | CM APPL.            |
             | 69294/2026          |
             | </br>IN             |
             | W.P.(C)-            |
             | 14369//202          |
             | 6                   |

The cell wraps every ~10 characters, mid-token ("14369//202" + "6"), and a
listed application names its case after a literal `</br>IN`. So each item's
case column is read as one whitespace-free string, split on `</br>IN` when
present, and the case is the first `TYPE-NUMBER//YEAR` in what remains.
Applications (CM APPL., CRL.M.A., I.A.) are never the case themselves.

An item whose case column holds only an application (no `IN <case>`) is
kept as an entry carrying the application token: it cannot match a case,
but the parse must account for every numbered item.
"""

from __future__ import annotations

import logging
import re

from ...base import CauseListEntry, ParsedDoc, RawDoc
from ...exceptions import CauseListParseError
from ...normalize import canonical_case_key
from .pdftext import ROW_TOLERANCE, Line, find_court_hall, find_list_date, read_lines

logger = logging.getLogger(__name__)

_ITEM = re.compile(r"^[1-9]\d{0,3}$")
_TOKEN = re.compile(r"^([A-Za-z][A-Za-z.()&\-]*?)-?(\d{1,7})/{1,2}(\d{4})")
_IN_MARKER = "</br>IN"
_APPLICATION = re.compile(r"^(CMAPPL|CRLMA|IA\w*|CM|CMP|CMA|MA)$")
_X_TOLERANCE = 6.0


def _compact(lines: list[Line]) -> str:
    return re.sub(r"\s+", "", "".join(ln.text for ln in lines))


def _case_from(text: str) -> str:
    """First case token of a whitespace-free case-column string."""
    if _IN_MARKER in text:
        text = text.split(_IN_MARKER, 1)[1]
    match = _TOKEN.match(text)
    if not match:
        return ""
    case_type, number, year = match.groups()
    return f"{case_type}/{number}/{year}"


def parse_delhi_doc(doc: RawDoc) -> ParsedDoc:
    lines, width = read_lines(doc.path)

    # Item numbers: bare integers in the left part of the page, in the most
    # populous x-cluster.
    candidates = [ln for ln in lines if ln.x0 < width * 0.30 and _ITEM.match(ln.text)]
    if not candidates:
        raise CauseListParseError("No item-number column found in the Delhi list.")
    clusters: list[list[Line]] = []
    for ln in sorted(candidates, key=lambda l: l.x0):
        if clusters and abs(ln.x0 - clusters[-1][0].x0) <= _X_TOLERANCE:
            clusters[-1].append(ln)
        else:
            clusters.append([ln])
    items = max(clusters, key=len)
    items.sort(key=lambda l: (l.page, -round(l.y1)))

    # The case column sits where the first item's row continues to the right.
    first = items[0]
    mates = sorted(
        (
            ln for ln in lines
            if ln.page == first.page and abs(ln.y1 - first.y1) <= ROW_TOLERANCE and ln.x0 > first.x1
        ),
        key=lambda l: l.x0,
    )
    if not mates:
        raise CauseListParseError("No case column beside the first Delhi item.")
    case_x = mates[0].x0
    case_lines = [ln for ln in lines if abs(ln.x0 - case_x) <= _X_TOLERANCE and ln.x0 > first.x1]

    header = " ".join(ln.text for ln in lines if ln.page == 0 and ln.y1 > first.y1) if first.page == 0 else ""
    list_date = find_list_date(header)
    court_hall = find_court_hall(header)

    positions = {id(ln): n for n, ln in enumerate(lines)}
    entries: list[CauseListEntry] = []
    for index, item in enumerate(items):
        nxt = items[index + 1] if index + 1 < len(items) else None
        start = positions[id(item)]
        end = positions[id(nxt)] if nxt is not None else len(lines)
        block = [
            ln for ln in case_lines
            if start <= positions[id(ln)] < end
        ] or [
            ln for ln in case_lines if (ln.page, -ln.y1) >= (item.page, -item.y1)
            and (nxt is None or (ln.page, -ln.y1) < (nxt.page, -nxt.y1))
        ]
        block.sort(key=lambda l: (l.page, -round(l.y1)))
        text = _compact(block)
        token = _case_from(text)
        if not token:
            raise CauseListParseError(
                f"Delhi item {item.text}: no case number in {text[:60]!r} -- layout changed?"
            )
        entries.append(
            CauseListEntry(
                item_number=item.text,
                case_token=token,
                court_hall=court_hall,
                bench=doc.bench_label,
                list_type=doc.list_type,
            )
        )

    unique_numbers = {int(e.item_number) for e in entries}
    span = max(unique_numbers) - min(unique_numbers) + 1
    if len(unique_numbers) >= 5 and (span - len(unique_numbers)) / span > 0.25:
        raise CauseListParseError("Delhi list: item numbers have large gaps -- refusing a partial parse.")
    return ParsedDoc(entries=entries, list_date=list_date)
