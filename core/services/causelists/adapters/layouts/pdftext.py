"""Coordinate-aware text reading shared by the layout parsers.

pdfminer's plain text order walks these lists column-block-wise and
separates an item number from the case number printed beside it, so rows
are rebuilt from geometry: every text LINE keeps its page, left edge (x0),
right edge (x1) and top (y1).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pdfminer.high_level import extract_pages
from pdfminer.layout import LAParams, LTTextLine

from ...exceptions import CauseListParseError

logger = logging.getLogger(__name__)

# One row's lines share a top edge to within rounding; this absorbs it.
ROW_TOLERANCE = 3.0


@dataclass(frozen=True)
class Line:
    page: int
    x0: float
    x1: float
    y1: float
    text: str


def read_lines(path: Path) -> tuple[list[Line], float]:
    """(lines in reading order, page width). Page by page, so memory stays
    bounded however long the document is."""
    lines: list[Line] = []
    width = 595.0
    try:
        for page_no, page in enumerate(extract_pages(str(path), laparams=LAParams())):
            width = float(page.width) or width

            def walk(obj):
                if isinstance(obj, LTTextLine):
                    text = obj.get_text().strip()
                    if text:
                        lines.append(Line(page_no, obj.x0, obj.x1, obj.y1, text))
                elif hasattr(obj, "__iter__"):
                    for child in obj:
                        walk(child)

            walk(page)
    except Exception as exc:  # noqa: BLE001 -- pdfminer raises many types
        raise CauseListParseError(f"Could not read the cause-list PDF: {exc}") from exc
    if not lines:
        raise CauseListParseError("Cause-list PDF contains no extractable text.")
    lines.sort(key=lambda ln: (ln.page, -round(ln.y1), ln.x0))
    return lines, width


_MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], 1)
}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS["sept"] = 9

_DATE_WORDS = re.compile(
    r"(\d{1,2})\s*(?:st|nd|rd|th)?\s*(?:day\s+of\s+)?([A-Za-z]{3,9})\.?,?\s*(\d{4})", re.IGNORECASE
)
# "MONDAY, OCTOBER 12, 2026" (Uttarakhand)
_DATE_MONTH_FIRST = re.compile(
    r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.IGNORECASE
)
_DATE_NUM = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\b")
_HALL = re.compile(
    r"COURT\s*(?:HALL)?\s*(?:NO\.?|NUMBER)?\s*[:\-]?\s*(\d{1,3}[A-Za-z]?)\b", re.IGNORECASE
)


def find_list_date(text: str) -> date | None:
    """First plausible date in header text: '12th October 2026',
    '12 TH OCTOBER, 2026', 'THE 12TH DAY OF OCTOBER 2026', '12/10/2026'."""
    squashed = re.sub(r"(\d)\s+(st|nd|rd|th)\b", r"\1\2", text or "", flags=re.IGNORECASE)
    for match in _DATE_WORDS.finditer(squashed):
        day, month_name, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                continue
    for match in _DATE_MONTH_FIRST.finditer(squashed):
        month_name, day, year = match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                continue
    for match in _DATE_NUM.finditer(squashed):
        day, month, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            continue
    return None


def find_court_hall(text: str) -> str:
    match = _HALL.search(text or "")
    return match.group(1) if match else ""
