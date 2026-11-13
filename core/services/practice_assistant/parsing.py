"""Reading a question's own words: amounts, fee categories, hearing dates,
report periods, draft kinds and the piece of text that names a case.

Pure functions, no database, no model. Everything here only proposes: a case
text goes through reads.resolve_case_candidates under the owner, an amount
and a category land on a card the advocate edits and confirms.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

MAX_AMOUNT = Decimal("9999999999.99")  # AppearanceFee.amount is 12 digits, 2 decimals

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
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

# Things that carry digits but are not money.
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SLASH_DATE_RE = re.compile(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b")
_TEXT_DATE_RE = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_RE})\b\.?(?:,?\s+(\d{{4}}))?", re.IGNORECASE
)
_MONTH_FIRST_RE = re.compile(
    rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.IGNORECASE
)
_CNR_RE = re.compile(r"\b(?=[A-Za-z0-9]*\d)[A-Za-z]{4}[A-Za-z0-9]{12}\b")
_CASE_NUMBER_RE = re.compile(r"\b[A-Za-z][A-Za-z.()]*\s?[/.\-]?\s?\d+\s?/\s?\d{4}\b")
_INVOICE_NO_RE = re.compile(r"\b[A-Za-z]{2,10}-\d{1,8}\b")

_AMOUNT_RE = re.compile(
    r"(?P<cur>₹|rs\.?|inr)?\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<suffix>k\b|lakhs?\b|lacs?\b|crores?\b)?",
    re.IGNORECASE,
)
_SUFFIX = {"k": Decimal(1000), "lakh": Decimal(100000), "lac": Decimal(100000), "crore": Decimal(10000000)}

CATEGORY_WORDS = (
    ("hotel", re.compile(r"\b(hotel|lodging|accommodation)\b", re.IGNORECASE)),
    ("flight", re.compile(r"\b(flights?|airfare|air\s*tickets?|air\s*fare)\b", re.IGNORECASE)),
    ("appearance", re.compile(r"\b(appearance|professional)\b", re.IGNORECASE)),
    (
        "other",
        re.compile(
            r"\bother\s+(?:fees?|charges?|expenses?|bills?|costs?)\b|\b(miscellaneous|misc|expenses?|conveyance|taxi|cab)\b",
            re.IGNORECASE,
        ),
    ),
)


def _mask(text: str, *patterns: re.Pattern) -> str:
    for pattern in patterns:
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


def mask_non_money(text: str, extra: tuple[str, ...] = ()) -> str:
    """`text` with dates, case numbers, CNRs and invoice numbers blanked out
    (same length), so the digits that remain are candidates for an amount.
    `extra` are literal strings (the owner's own invoice numbers) to blank."""
    for literal in extra:
        if literal:
            text = re.sub(re.escape(literal), lambda m: " " * len(m.group(0)), text, flags=re.IGNORECASE)
    return _mask(
        text,
        _ISO_RE,
        _SLASH_DATE_RE,
        _TEXT_DATE_RE,
        _MONTH_FIRST_RE,
        _CNR_RE,
        _CASE_NUMBER_RE,
        _INVOICE_NO_RE,
    )


def parse_amount(text: str, *, extra_mask: tuple[str, ...] = ()) -> Optional[Decimal]:
    """The last amount in `text`: Rs 15,000, 15000, 15k, 1.5 lakh. A bare
    number with no currency mark, suffix or comma grouping must have at least
    three digits (so "2 fees" or "hearing 3" is not read as money). None when
    nothing usable; also None for an amount that would not fit the column."""
    cleaned = mask_non_money(text or "", extra_mask)
    found: Optional[Decimal] = None
    for match in _AMOUNT_RE.finditer(cleaned):
        number = match.group("num").replace(",", "").rstrip(".")
        suffix = (match.group("suffix") or "").lower().rstrip("s")
        marked = bool(match.group("cur")) or bool(suffix) or "," in match.group("num")
        if not marked and len(number.split(".")[0]) < 3:
            continue
        try:
            value = Decimal(number)
        except InvalidOperation:
            continue
        if suffix:
            value *= _SUFFIX[suffix]
        value = value.quantize(Decimal("0.01"))
        if value <= 0 or value > MAX_AMOUNT:
            continue
        found = value
    return found


def parse_category(text: str, default: Optional[str] = None) -> Optional[str]:
    """The first fee category named in `text` (hotel, flight, appearance,
    other), else `default`."""
    best: tuple[int, str] | None = None
    for name, pattern in CATEGORY_WORDS:
        match = pattern.search(text or "")
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), name)
    return best[1] if best else default


_CATEGORY_CHANGE_RE = re.compile(
    r"\b(?:category|type|kind)\s+(?:to|as|=)\s+(?:an?\s+)?(\w+)|\bto\s+(?:an?\s+)?(hotel|flight|appearance|other)\b",
    re.IGNORECASE,
)


def parse_category_change(text: str) -> Optional[str]:
    """A category an update asks for ("category to hotel", "to hotel")."""
    match = _CATEGORY_CHANGE_RE.search(text or "")
    if not match:
        return None
    return parse_category(match.group(1) or match.group(2))


_DESCRIPTION_RE = re.compile(
    r"\b(?:description|notes?|remarks?|narration)\s*(?:to|as|:|=)\s*[\"']?(.+?)[\"']?\s*$",
    re.IGNORECASE,
)


def parse_description(text: str) -> Optional[str]:
    match = _DESCRIPTION_RE.search((text or "").strip())
    if not match:
        return None
    value = match.group(1).strip()
    return value[:500] or None


def parse_dates(text: str, *, today: date) -> list[date]:
    """Calendar dates named in `text`: 2026-11-12, 12/11/2026 (day first),
    12 Nov, 12 November 2026, Nov 12. A date with no year takes `today`'s."""
    found: list[date] = []

    def add(year: int, month: int, day: int) -> None:
        try:
            found.append(date(year, month, day))
        except ValueError:
            pass

    for m in _ISO_RE.finditer(text or ""):
        add(*map(int, m.group(0).split("-")))
    for m in _SLASH_DATE_RE.finditer(text or ""):
        parts = re.split(r"[/.\-]", m.group(0))
        day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
        add(year + 2000 if year < 100 else year, month, day)
    for m in _TEXT_DATE_RE.finditer(text or ""):
        add(int(m.group(3) or today.year), _MONTHS[m.group(2).lower()], int(m.group(1)))
    for m in _MONTH_FIRST_RE.finditer(text or ""):
        add(int(m.group(3) or today.year), _MONTHS[m.group(1).lower()], int(m.group(2)))
    return found


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------


def financial_year_start(day: date) -> date:
    """April 1 of the Indian financial year that contains `day`."""
    return date(day.year if day.month >= 4 else day.year - 1, 4, 1)


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    return first, nxt - timedelta(days=1)


def _quarter_bounds(day: date, offset: int = 0) -> tuple[date, date]:
    """The calendar quarter containing `day`, shifted by `offset` quarters."""
    index = (day.year * 4 + (day.month - 1) // 3) + offset
    year, quarter = divmod(index, 4)
    first_month = quarter * 3 + 1
    return date(year, first_month, 1), _month_bounds(year, first_month + 2)[1]


_RANGE_RE = re.compile(r"\b(?:from|between)\s+(.+?)\s+(?:to|till|until|and|-)\s+(.+?)(?:$|[,.?!])", re.IGNORECASE)


def parse_period(text: str, *, today: date) -> Optional[tuple[date, date]]:
    """The date range a question asks for, or None when it names none.
    Understands: from X to Y (two dates), this/last month, this/last quarter,
    this/last financial year (April to March), this/last year (calendar),
    this/next week, next N days, last N days, today, tomorrow."""
    t = " ".join((text or "").lower().split())

    range_match = _RANGE_RE.search(t)
    if range_match:
        first = parse_dates(range_match.group(1), today=today)
        second = parse_dates(range_match.group(2), today=today)
        if first and second:
            start, end = first[0], second[0]
            if start <= end:
                return start, end

    if re.search(r"\b(?:this|current)\s+(?:financial|fiscal)\s+year\b|\bthis\s+fy\b|\bcurrent\s+fy\b", t):
        start = financial_year_start(today)
        return start, date(start.year + 1, 3, 31)
    if re.search(r"\blast\s+(?:financial|fiscal)\s+year\b|\blast\s+fy\b|\bprevious\s+(?:financial|fiscal)\s+year\b", t):
        start = date(financial_year_start(today).year - 1, 4, 1)
        return start, date(start.year + 1, 3, 31)
    if re.search(r"\bthis\s+quarter\b", t):
        return _quarter_bounds(today)
    if re.search(r"\b(?:last|previous)\s+quarter\b", t):
        return _quarter_bounds(today, -1)
    if re.search(r"\bthis\s+month\b", t):
        return _month_bounds(today.year, today.month)
    if re.search(r"\b(?:last|previous)\s+month\b", t):
        year, month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        return _month_bounds(year, month)
    if re.search(r"\bnext\s+month\b", t):
        year, month = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
        return _month_bounds(year, month)
    if re.search(r"\bthis\s+year\b", t):
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if re.search(r"\blast\s+year\b", t):
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    days = re.search(r"\bnext\s+(\d{1,3})\s+days?\b", t)
    if days:
        return today, today + timedelta(days=int(days.group(1)))
    days = re.search(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", t)
    if days:
        return today - timedelta(days=int(days.group(1))), today
    if re.search(r"\bthis\s+week\b", t):
        start = today - timedelta(days=today.weekday())
        return start, start + timedelta(days=6)
    if re.search(r"\bnext\s+week\b", t):
        start = today - timedelta(days=today.weekday()) + timedelta(days=7)
        return start, start + timedelta(days=6)
    if re.search(r"\btomorrow\b", t):
        return today + timedelta(days=1), today + timedelta(days=1)
    if re.search(r"\btoday\b", t):
        return today, today
    return None


# ---------------------------------------------------------------------------
# Case text, draft kinds, report kinds
# ---------------------------------------------------------------------------

_PARTIES_RE = re.compile(
    r"([A-Za-z][\w.&'()-]*(?:\s+[\w.&'()-]+){0,3}?)\s+(v\.?|vs\.?|versus)\s+([\w.&'()-]+(?:\s+[\w.&'()-]+){0,3})",
    re.IGNORECASE,
)
_LEADING_RE = re.compile(r"^(?:the|my|a|an|this|that)\s+", re.IGNORECASE)
_TRAILING_RE = re.compile(r"\s+(?:case|matter|file|hearing|suit|petition|appeal)s?$", re.IGNORECASE)
_PREPOSITION_RE = re.compile(r"\s(?:for|in|on|of|against|regarding|about|to)\s+", re.IGNORECASE)

_BEFORE_NOUN_RE = re.compile(
    r"\b(?:change|update|edit|delete|remove|correct|revise|generate|create|raise|issue|add|record|log|"
    r"bump|hike|increase|reduce|lower|cut|decrease)\s+"
    r"(?:the\s+|a\s+|an\s+)?(?:new\s+)?(.+?)\s+(?:fee|invoice|charge|bill|hotel|flight)s?\b",
    re.IGNORECASE,
)

_NOISE_WORDS = {
    "fee", "fees", "invoice", "invoices", "hotel", "flight", "appearance", "charge", "charges", "it", "this",
    "that", "me", "us", "all", "now", "today", "yesterday", "tomorrow", "the", "a", "an", "my", "pending",
    "latest", "last", "new", "old", "unpaid", "paid", "sent",
}


_PERSON_RE = re.compile(
    r"\b(?:to|for|with|client|of|in)\s+((?:[A-Z]\.\s?){0,3}[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b"
)


def case_text_needles(query: str) -> list[str]:
    """Pieces of the question that may name a case, most specific first: a
    CNR or case number, the two parties of "A vs B" (whole, then each side),
    then the words after the last for/in/on/of. Duplicates removed."""
    needles: list[str] = []
    token = _CNR_RE.search(query) or _CASE_NUMBER_RE.search(query)
    if token:
        needles.append(token.group(0).strip())
    parties = _PARTIES_RE.search(query)
    if parties:
        # "add a fee for Rao vs State on 12 Nov": the left side runs back to
        # the last preposition, the right side forward to the first one.
        left = _PREPOSITION_RE.split(" " + parties.group(1))[-1].strip()
        right = _PREPOSITION_RE.split(" " + parties.group(3))[0].strip()
        needles += [f"{left} {parties.group(2)} {right}", left, right]
    # A person named the way people write names: "a letter to K. Rao",
    # "the fee for Sharma" (capitalised words after to/for/with/client).
    for name in _PERSON_RE.findall(query):
        needles.append(name.strip())
    before = _BEFORE_NOUN_RE.search(query)
    if before:
        needles.append(_TRAILING_RE.sub("", _LEADING_RE.sub("", before.group(1).strip())).strip())
    parts = _PREPOSITION_RE.split(" " + query.strip().rstrip("?.! "))
    if len(parts) > 1:
        tail = _TRAILING_RE.sub("", _LEADING_RE.sub("", parts[-1].strip())).strip()
        if (
            tail
            and not parse_dates(tail, today=date(2000, 1, 1))
            and parse_amount(tail) is None
            and not re.fullmatch(r"[\d,.\s]+(?:k|lakhs?|lacs?)?", tail, re.IGNORECASE)
        ):
            needles.append(tail)
    seen: set[str] = set()
    out: list[str] = []
    for needle in needles:
        key = needle.casefold()
        if len(needle) >= 3 and key not in seen and key not in _NOISE_WORDS:
            seen.add(key)
            out.append(needle[:200])
    return out


DRAFT_SUBTYPE_PATTERNS = (
    ("list_of_dates", re.compile(r"\b(list\s+of\s+dates(?:\s+and\s+events)?|synopsis\s+of\s+dates|dates\s+and\s+events|chronology)\b", re.IGNORECASE)),
    ("client_letter", re.compile(r"\b(client\s+letter|letter|email\s+to\s+(?:the\s+)?client|update\s+for\s+(?:the\s+)?client)\b", re.IGNORECASE)),
    ("status_memo", re.compile(r"\b(status\s+memo|case\s+memo|memo|memorandum|status\s+note\s+for\s+file)\b", re.IGNORECASE)),
    ("personal_note", re.compile(r"\b(personal\s+note|working\s+note|note\s+to\s+self|note)\b", re.IGNORECASE)),
)
_DRAFT_VERB_RE = re.compile(r"\b(draft|write|prepare|compose|start|begin|make)\b", re.IGNORECASE)


def parse_draft_request(text: str) -> Optional[str]:
    """The draft subtype a question asks to start ("draft a client letter for
    Rao", "write a list of dates"), or None when it is not such a request."""
    if not _DRAFT_VERB_RE.search(text or ""):
        return None
    for subtype, pattern in DRAFT_SUBTYPE_PATTERNS:
        if pattern.search(text):
            return subtype
    return None


REPORT_KIND_PATTERNS = (
    ("billing", re.compile(r"\b(billing|invoices?|fees?|payments?|outstanding|receivables?|income|revenue|earnings)\b", re.IGNORECASE)),
    ("hearings", re.compile(r"\b(hearings?|calendar|cause\s*lists?|court\s+dates?)\b", re.IGNORECASE)),
    ("deadlines", re.compile(r"\b(deadlines?|tasks?|to-?dos?|overdue|limitation)\b", re.IGNORECASE)),
    ("cases", re.compile(r"\b(cases?|matters?|portfolio|caseload)\b", re.IGNORECASE)),
)
_REPORT_WORD_RE = re.compile(
    r"\b(reports?|export|docx|(?:as|in)\s+(?:an?\s+)?(?:pdf|word)|word\s+(?:file|document)|printout)\b",
    re.IGNORECASE,
)

# A request to change a fee starts with its verb ("add a hotel fee ...",
# "please change INV-0042 to 20000"), so a question that merely mentions one
# ("which fees were added") is not read as a command.
_LEAD = r"^(?:(?:please|kindly)\s+|(?:can|could|would|will)\s+you\s+|i\s+(?:want|need|would\s+like)\s+to\s+|let'?s\s+)*"
_FEE_NOUN = r"(?:\b(?:fees?|charges?|invoices?|bills?|expenses?|amount)\b|\b[a-z]{2,10}-\d{1,8}\b)"
_MUTATION_VERBS = (
    ("propose_fee_delete", re.compile(_LEAD + r"(?:delete|remove|discard|drop|cancel)\b.*" + _FEE_NOUN, re.IGNORECASE)),
    (
        "propose_fee_update",
        re.compile(
            _LEAD
            + r"(?:(?:change|update|edit|correct|revise|modify|amend|reduce|increase)\b.*"
            + _FEE_NOUN
            + r"|set\b.*"
            + _FEE_NOUN
            + r".*\bto\b)",
            re.IGNORECASE,
        ),
    ),
    (
        # "bump the Rao fee up by 2k", "reduce INV-0004 by 500": a change by
        # an amount (see parse_amount_change), before "raise an invoice".
        "propose_fee_update",
        re.compile(
            _LEAD + r"(?:bump|hike|raise|increase|reduce|lower|cut|decrease|drop)\b.*" + _FEE_NOUN + r".*\bby\b",
            re.IGNORECASE,
        ),
    ),
    (
        "propose_invoice_generate",
        re.compile(_LEAD + r"(?:generate|create|raise|issue|prepare|make|draw\s+up)\b.*\binvoices?\b", re.IGNORECASE),
    ),
    (
        "propose_fee_create",
        re.compile(
            _LEAD + r"(?:add|create|record|log|enter|book)\b.*\b(?:fees?|charges?|hotel|flights?|expenses?|bill)\b",
            re.IGNORECASE,
        ),
    ),
)


_UP_BY_RE = re.compile(r"\b(?:up|bump\w*|hike\w*|raise\w*|increase\w*|add)\b.*\bby\b|\bby\b.*\bmore\b", re.IGNORECASE)
_DOWN_BY_RE = re.compile(r"\b(?:down|reduce\w*|lower\w*|cut\w*|decrease\w*|drop\w*)\b.*\bby\b|\bby\b.*\bless\b", re.IGNORECASE)


def parse_amount_change(text: str) -> int:
    """+1 when the question changes an amount up BY something ("bump it up by
    2k"), -1 when down by something, 0 when it names the new amount itself."""
    if _DOWN_BY_RE.search(text or ""):
        return -1
    if _UP_BY_RE.search(text or ""):
        return 1
    return 0


def parse_fee_mutation(text: str) -> Optional[str]:
    """The fee-changing intent a command asks for, or None. First match of:
    delete, update, generate invoice, add."""
    for intent, pattern in _MUTATION_VERBS:
        if pattern.search(text or ""):
            return intent
    return None


def wants_report(text: str) -> bool:
    return bool(_REPORT_WORD_RE.search(text or ""))


def parse_report_kind(text: str) -> Optional[str]:
    """The report kind a question names, or None. The earliest-mentioned kind
    wins ("a billing report of cases" is billing)."""
    best: tuple[int, str] | None = None
    for name, pattern in REPORT_KIND_PATTERNS:
        match = pattern.search(text or "")
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), name)
    return best[1] if best else None
