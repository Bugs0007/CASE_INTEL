"""Work out when a court-order direction falls due, from its text.

Input is one direction string from an order summary, e.g. "Respondent to
file counter affidavit within four (4) weeks." -- already short and
normalised by the summariser. Deadlines in Indian orders use a small,
closed vocabulary, so this is a regex table rather than a second LLM call:
deterministic, free, and every phrasing it handles is a test case.

Precedence, most specific first:
  1. an explicit date        "by 12.10.2026", "on or before 12th October 2026"
  2. a period from the order "within 4 weeks", "within a fortnight"
  3. the next hearing        "before the next date of hearing"
  4. immediately             "forthwith"
  5. no period stated        -> next hearing date if one is known, else no date

A period that runs from some later event -- receipt of a copy, service, or
"thereafter" (after an earlier step) -- is still counted from the order
date, since that event's date isn't known here, and flagged `approximate`
so the task can say so. Counting from the order date can only make the
date earlier than the real one, never later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from core.models import Task
from core.services.order_summary.routing import normalize

_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty five": 45,
    "forty-five": 45,
    "sixty": 60,
    "ninety": 90,
}
_NUMBER = r"\d{1,3}|" + "|".join(
    sorted((re.escape(w) for w in _NUMBER_WORDS), key=len, reverse=True)
)

_MONTHS = {
    name: index
    for index, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
_MONTH = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DEADLINE_LEAD = r"(?:by|on\s+or\s+before|before|not\s+later\s+than|till|until)"

# "by 12.10.2026" / "on or before 12-10-26" -- day first, as Indian orders are.
_NUMERIC_DATE_RE = re.compile(
    _DEADLINE_LEAD + r"\s+(?P<d>\d{1,2})[./-](?P<m>\d{1,2})[./-](?P<y>\d{4}|\d{2})\b",
    re.IGNORECASE,
)
# "by 12th October 2026" / "on or before 12 Oct, 2026"
_DAY_MONTH_DATE_RE = re.compile(
    _DEADLINE_LEAD
    + r"\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<mon>"
    + _MONTH
    + r")\.?,?\s+(?P<y>\d{4})\b",
    re.IGNORECASE,
)
# "by October 12, 2026"
_MONTH_DAY_DATE_RE = re.compile(
    _DEADLINE_LEAD
    + r"\s+(?P<mon>"
    + _MONTH
    + r")\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})\b",
    re.IGNORECASE,
)
# "within four (4) weeks" / "within a period of 30 days" / "within 2 months"
_PERIOD_RE = re.compile(
    r"within\s+(?:a\s+(?:period|time)\s+of\s+)?"
    r"(?P<n>" + _NUMBER + r")\s*"
    r"(?:\(\s*(?:" + _NUMBER + r")\s*\)\s*)?"
    r"(?P<unit>day|week|month|year)s?\b",
    re.IGNORECASE,
)
_FORTNIGHT_RE = re.compile(r"within\s+(?:a\s+)?fortnight", re.IGNORECASE)
# The period starts after an event whose date isn't known here.
_LATER_START_RE = re.compile(
    r"receipt\s+of\s+(?:a\s+)?(?:certified\s+)?cop(?:y|ies)"
    r"|\bthereafter\b"
    r"|(?:from|after)\s+(?:the\s+date\s+of\s+)?service\b",
    re.IGNORECASE,
)
_NEXT_HEARING_RE = re.compile(
    r"(?:by|before|on\s+or\s+before|prior\s+to)\s+the\s+next\s+(?:date\s+(?:of\s+)?)?(?:hearing|date)",
    re.IGNORECASE,
)
_FORTHWITH_RE = re.compile(r"\b(?:forthwith|immediately)\b", re.IGNORECASE)


@dataclass(frozen=True)
class DirectionDueDate:
    due_date: date | None
    basis: str  # a Task.BASIS_* constant, or "" when no date could be set
    approximate: bool = False


def parse_direction_due_date(
    text: str, *, order_date: date, next_hearing_date: date | None
) -> DirectionDueDate:
    """Due date for one direction. Pure -- no DB access."""
    normalized = normalize(text)

    explicit = _explicit_date(normalized)
    if explicit is not None:
        return DirectionDueDate(explicit, Task.BASIS_EXPLICIT_DATE)

    period = _period_from_order(normalized, order_date)
    if period is not None:
        return DirectionDueDate(
            period,
            Task.BASIS_RELATIVE_TO_ORDER,
            approximate=bool(_LATER_START_RE.search(normalized)),
        )

    if _NEXT_HEARING_RE.search(normalized):
        return _next_hearing(next_hearing_date)

    if _FORTHWITH_RE.search(normalized):
        return DirectionDueDate(order_date, Task.BASIS_RELATIVE_TO_ORDER)

    return _next_hearing(next_hearing_date)


def _next_hearing(next_hearing_date: date | None) -> DirectionDueDate:
    if next_hearing_date is None:
        return DirectionDueDate(None, "")
    return DirectionDueDate(next_hearing_date, Task.BASIS_NEXT_HEARING_FALLBACK)


def _explicit_date(text: str) -> date | None:
    for pattern in (_NUMERIC_DATE_RE, _DAY_MONTH_DATE_RE, _MONTH_DAY_DATE_RE):
        match = pattern.search(text)
        if not match:
            continue
        month = (
            _MONTHS[match.group("mon").lower()]
            if "mon" in pattern.groupindex
            else int(match.group("m"))
        )
        year = int(match.group("y"))
        if year < 100:
            year += 2000
        try:
            return date(year, month, int(match.group("d")))
        except ValueError:
            continue  # "31.02.2026" -- not a date; try the next phrasing
    return None


def _period_from_order(text: str, order_date: date) -> date | None:
    if _FORTNIGHT_RE.search(text):
        return order_date + timedelta(days=14)

    match = _PERIOD_RE.search(text)
    if not match:
        return None
    raw = match.group("n").lower()
    amount = int(raw) if raw.isdigit() else _NUMBER_WORDS[re.sub(r"\s+", " ", raw)]
    unit = match.group("unit").lower()
    if unit == "day":
        return order_date + timedelta(days=amount)
    if unit == "week":
        return order_date + timedelta(weeks=amount)
    if unit == "month":
        return order_date + relativedelta(months=amount)
    return order_date + relativedelta(years=amount)
