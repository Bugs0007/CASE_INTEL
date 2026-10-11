"""The common High Court list layout: an item number at the left, the case
number beside it, parties and advocates to the right.

Courts differ in the details this parser absorbs (all seen in real lists,
2026-10-10):

  Bombay, Madras, Patna, Calcutta, Rajasthan...  item `1` and case `WP/..` in
                                                  separate text lines
  Gauhati, Chhattisgarh, Tripura, Sikkim, J&K    item and case in ONE line
                                                  (`1 WP(C)/150/2026`,
                                                  `1. WA 915/2026`, `1) WP(C)/733/2026`)
  Karnataka                                       `WP 200448/2025`, sub-item `1.1`
  Orissa                                          `[ ODHC010687532026 ]` under the case

Columns are DETECTED per document (the item column is the x-cluster with
the most item-shaped lines), never hardcoded, because a fixed offset parses
some layouts as empty -- which reads exactly like "your case isn't listed".

Completeness guard: before returning, the parse is reconciled against two
independent counts (item-shaped lines found, distinct case numbers printed
in the case column). A parse that recovers materially fewer than either is
raised as a failure instead of returned, since a dropped half of a list is
the same wrong answer as a dropped whole.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from ...base import CauseListEntry, ParsedDoc, RawDoc
from ...exceptions import CauseListParseError
from ...normalize import canonical_case_key
from .pdftext import ROW_TOLERANCE, Line, find_court_hall, find_list_date, read_lines

logger = logging.getLogger(__name__)

# TYPE (letters, dots, brackets) then NUMBER/YEAR, separators '/', ' ' or '-'
# The type may hold a word break ("MAC App./94/2023", "Cont.Cas(C)/62/2026").
_CASE = r"[A-Za-z][A-Za-z.()&]{0,20}(?:\s[A-Za-z.()&]{1,12}){0,2}[ /\-]\s*\d{1,7}\s*/\s*\d{4}"
_CASE_AT_START = re.compile(rf"^\s*(?P<case>{_CASE})")
# Item numbers never start with 0 ("0003)" is the tail of an application id).
# 'wt7' = a matter tagged to item 7 (Calcutta, like Telangana's 'wt4').
_STANDALONE_ITEM = re.compile(r"^(?P<item>(?:wt\s*)?[1-9]\d{0,3}(?:\.\d{1,3})?)\s*[.)]?$", re.IGNORECASE)
_COMBINED_ITEM = re.compile(
    rf"^(?P<item>(?:wt\s*)?[1-9]\d{{0,3}}(?:\.\d{{1,3}})?)\s*(?:[.)]\s*|\s+)(?P<rest>{_CASE}.*)$",
    re.DOTALL | re.IGNORECASE,
)
_COMBINED_APPLICATION = re.compile(
    r"^(?P<item>[1-9]\d{0,3}(?:\.\d{1,3})?)\s*[.)]\s*(?:IA|I\.A\.|CM|C\.M\.|CMP|MA|CMA|WMP)\b",
    re.IGNORECASE,
)
# "3) With" -- tagged to the previous item, no case number of its own.
_WITH_ITEM = re.compile(r"^(?P<item>[1-9]\d{0,3})\s*[.)]\s*with\b", re.IGNORECASE)
_CNR = re.compile(r"\b([A-Z]{4}\d{12})\b")
_CONNECTED = re.compile(r"^(IA|I\.A\.|CM|C\.M\.|CMP|MA|CMA)\b|^\d+\.\(\d+\)\s", re.IGNORECASE)
# Applications filed within a case (never the case itself): IA, IA(ST),
# CM, CMP, MA, CMA. 'MAT' (a real appeal type) must NOT match, hence exact.
_APPLICATION_TYPE = re.compile(r"^(IA\w*|CM|CMP|CMA|MA|WMP)$")

_X_TOLERANCE = 6.0
# Share of page width within which an item number must start.
_ITEM_ZONE = 0.30
_MIN_PAIRED_RATIO = 0.90
_MIN_CASE_COVERAGE = 0.85
_MAX_ITEM_GAP_RATIO = 0.25


@dataclass
class _Item:
    line: Line
    number: str
    case_token: str  # "" until paired
    case_line: Line | None
    application_row: bool = False


def _is_application(case_token: str) -> bool:
    key = canonical_case_key(case_token)
    return bool(key and _APPLICATION_TYPE.match(key[0]))


_LEADING_IN = re.compile(r"^in\s+(?=[A-Za-z])", re.IGNORECASE)


def _first_case(text: str) -> str:
    match = _CASE_AT_START.match(text)
    if not match:
        return ""
    token = re.sub(r"\s+", " ", match.group("case")).strip()
    # "in RFA/35/2024": an application naming the case it is filed in.
    return _LEADING_IN.sub("", token)


_APPLICATION_ROW = re.compile(r"^(IA|I\.A\.|CM|C\.M\.|CMP|MA|CMA|WMP)\b", re.IGNORECASE)


def parse_table_doc(doc: RawDoc) -> ParsedDoc:
    lines, width = read_lines(doc.path)
    zone = width * _ITEM_ZONE
    by_page: dict[int, list[Line]] = {}
    for ln in lines:
        by_page.setdefault(ln.page, []).append(ln)

    def row_mates(item_line: Line) -> list[Line]:
        return sorted(
            (
                ln for ln in by_page[item_line.page]
                if abs(ln.y1 - item_line.y1) <= ROW_TOLERANCE and ln.x0 > item_line.x1 - 1
            ),
            key=lambda l: l.x0,
        )

    candidates: list[_Item] = []
    with_numbers: set[int] = set()
    for ln in lines:
        if ln.x0 > zone:
            continue
        standalone = _STANDALONE_ITEM.match(ln.text)
        if standalone:
            item = _Item(ln, standalone.group("item"), "", None)
            for mate in row_mates(ln):
                token = _first_case(mate.text)
                if token and not _is_application(token):
                    item.case_token, item.case_line = token, mate
                    break
                if token or _APPLICATION_ROW.match(mate.text):
                    item.application_row = True
                    break
            if item.case_token or item.application_row:
                candidates.append(item)
            continue
        combined = _COMBINED_ITEM.match(ln.text)
        if combined:
            token = _first_case(combined.group("rest"))
            if token and _is_application(token):
                # "13) IA NO. 1/2025 ... IN LA.App./20/2026": the case is the
                # one named further down, found in the second pass below.
                candidates.append(_Item(ln, combined.group("item"), "", None, application_row=True))
                continue
            if token:
                candidates.append(_Item(ln, combined.group("item"), token, ln))
                continue
        application = _COMBINED_APPLICATION.match(ln.text)
        if application:
            candidates.append(_Item(ln, application.group("item"), "", None, application_row=True))
            continue
        tagged_with = _WITH_ITEM.match(ln.text)
        if tagged_with:
            with_numbers.add(int(tagged_with.group("item")))

    if not candidates:
        raise CauseListParseError("No item-number column found -- the layout may have changed.")

    # The item column: the x-cluster holding the most candidates. Candidates
    # already had to sit beside a case number (or an application), so stray
    # digits elsewhere (page-number footers) cannot form a rival column.
    clusters: list[list[_Item]] = []
    for cand in sorted(candidates, key=lambda c: c.line.x0):
        if clusters and abs(cand.line.x0 - clusters[-1][0].line.x0) <= _X_TOLERANCE:
            clusters[-1].append(cand)
        else:
            clusters.append([cand])
    biggest = max(len(c) for c in clusters)
    items = min((c for c in clusters if len(c) >= 0.6 * biggest), key=lambda c: c[0].line.x0)
    items.sort(key=lambda c: (c.line.page, -round(c.line.y1), c.line.x0))
    item_x = min(c.line.x0 for c in items)

    # An item that is an APPLICATION ("IA NO. 3/2026 ... IN MAC App./94/2023")
    # belongs to the case printed further down its own block.
    positions = {id(ln): n for n, ln in enumerate(lines)}
    for index, it in enumerate(items):
        if it.case_token:
            continue
        end = positions[id(items[index + 1].line)] if index + 1 < len(items) else len(lines)
        for ln in lines[positions[id(it.line)] + 1:end]:
            if it.line.x0 + 5 <= ln.x0 <= it.line.x1 + 60:
                token = _first_case(ln.text)
                if token and not _is_application(token):
                    it.case_token, it.case_line = token, ln
                    break

    # An application with no main case printed (Gauhati's `I.A.(Civil)/177/2026`)
    # is still a numbered item the parse must account for; it cannot match a
    # case (its type is an application type), but it must not look like a
    # dropped row.
    for it in items:
        if not it.case_token and it.application_row:
            row = next(iter(row_mates(it.line)), None)
            token = _first_case(row.text) if row is not None else ""
            if token:
                it.case_token, it.case_line = token, row
    paired = [it for it in items if it.case_token]
    if not paired:
        raise CauseListParseError(
            "Item numbers found but no case number beside any of them -- layout changed?"
        )
    if len(paired) / len(items) < _MIN_PAIRED_RATIO:
        raise CauseListParseError(
            f"Only {len(paired)} of {len(items)} item numbers have a case number beside them."
        )

    header_text = " ".join(
        ln.text for ln in lines if ln.page == 0 and ln.y1 > items[0].line.y1
    ) if items[0].line.page == 0 else " ".join(ln.text for ln in lines if ln.page == 0)
    list_date = find_list_date(header_text)
    court_hall = find_court_hall(header_text)

    # The case column: where the paired case numbers start.
    case_x = sorted(
        (it.case_line.x0 for it in paired if it.case_line is not None and it.case_line is not it.line)
    )
    case_col_x = case_x[len(case_x) // 2] if case_x else None

    entries: list[CauseListEntry] = []
    for index, it in enumerate(paired):
        nxt = paired[index + 1] if index + 1 < len(paired) else None
        start = positions[id(it.line)] + 1
        end = positions[id(nxt.line)] if nxt is not None else len(lines)
        cnr, connected, tagged = _extent_details(it, lines[start:end], case_col_x)
        base_kwargs = dict(
            court_hall=court_hall, bench=doc.bench_label, list_type=doc.list_type
        )
        entries.append(
            CauseListEntry(
                item_number=re.sub(r"\s+", "", it.number).rstrip(".)"),
                case_token=it.case_token,
                cnr=cnr,
                connected=connected,
                is_filing_number=bool(re.search(r"filing\s*no", it.case_token, re.IGNORECASE)),
                **base_kwargs,
            )
        )
        # Matters printed in the case column under this item ("with
        # WP/3668/2026") are heard together with it: listed, tagged to it.
        own = canonical_case_key(it.case_token)
        seen = {own}
        for token in tagged:
            key = canonical_case_key(token)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                CauseListEntry(
                    item_number=f"{it.number.rstrip('.)')} (connected)",
                    case_token=token,
                    **base_kwargs,
                )
            )

    _reconcile(entries, items, lines, case_col_x, item_x, with_numbers)
    return ParsedDoc(entries=entries, list_date=list_date)


def _extent_details(it: _Item, region: list[Line], case_x: float | None):
    """(CNR, connected IA lines, tagged case tokens) printed under this item,
    up to the next item -- across page breaks."""
    cnr = ""
    connected: list[str] = []
    tagged: list[str] = []
    left = (case_x if case_x is not None else it.line.x0) - 8
    for ln in region:
        if ln.x0 < left:
            continue
        found = _CNR.search(ln.text)
        if found and not cnr:
            cnr = found.group(1)
        if _CONNECTED.match(ln.text) and len(connected) < 20:
            connected.append(re.sub(r"\s+", " ", ln.text)[:80])
        if case_x is not None and abs(ln.x0 - case_x) <= _X_TOLERANCE:
            token = _first_case(ln.text)
            if token and not _is_application(token):
                tagged.append(token)
    return cnr, tuple(connected), tagged


def _integer_part(number: str) -> int | None:
    match = re.search(r"\d+", number or "")
    return int(match.group()) if match else None


def _reconcile(entries, items, lines, case_x, item_x, with_numbers=frozenset()) -> None:
    """Fail loudly when the parse recovered materially less than is printed."""
    # Item numbers run 1..N with only the odd gap (a withdrawn item). A
    # parse missing a large share of that range has dropped rows.
    numbers = sorted(
        {n for n in (_integer_part(e.item_number) for e in entries) if n is not None} | set(with_numbers)
    )
    if len(numbers) >= 5:
        span = numbers[-1] - numbers[0] + 1
        if (span - len(numbers)) / span > _MAX_ITEM_GAP_RATIO:
            raise CauseListParseError(
                f"Item numbers {numbers[0]}..{numbers[-1]} but only {len(numbers)} recovered -- "
                "refusing a partial parse."
            )
    if case_x is None:
        return
    printed: set = set()
    for ln in lines:
        if abs(ln.x0 - case_x) > _X_TOLERANCE:
            continue
        token = _first_case(ln.text)
        if not token or _is_application(token):
            continue
        key = canonical_case_key(token)
        if key:
            printed.add(key)
    parsed = {canonical_case_key(e.case_token) for e in entries} - {None}
    if printed and len(parsed & printed) / len(printed) < _MIN_CASE_COVERAGE:
        raise CauseListParseError(
            f"Parsed {len(parsed & printed)} of {len(printed)} case numbers printed in the case "
            f"column -- refusing a partial parse (a dropped case reads as 'not listed')."
        )
