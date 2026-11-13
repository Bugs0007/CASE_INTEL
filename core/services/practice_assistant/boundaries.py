"""What the practice assistant says when a question is outside what it can do,
and the small reading aids that keep keyword rules from misreading a question.

Pure functions, no database, no model:

  - `normalise_words`: common shorthand and misspellings ("tmrw", "hearngs").
  - `boundary_message`: a fixed, honest answer for questions the assistant
    cannot handle yet (general law, court filings, comparing or ranking,
    tasks, marking paid, billing many hearings at once, emailing clients).
    Checked before the keyword rules, so a question is never answered with a
    list that happens to share a word with it.
  - `split_request`: "list my hearings and email the clients" -> two parts,
    so the second part is named in the answer instead of silently dropped.
  - `wants_hearing_brief`, `wants_earnings`, `wants_attention`,
    `named_case_text`: phrasings the rules route to an existing read.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

# ---------------------------------------------------------------------------
# Shorthand and misspellings
# ---------------------------------------------------------------------------

_WORD_FIXES = {
    "tmrw": "tomorrow", "tmr": "tomorrow", "tmrow": "tomorrow", "tmrrw": "tomorrow", "tomo": "tomorrow",
    "tomorow": "tomorrow", "tommorow": "tomorrow", "tommorrow": "tomorrow", "2moro": "tomorrow",
    "2day": "today", "tdy": "today", "tday": "today",
    "hearngs": "hearings", "hearigns": "hearings", "hrngs": "hearings", "heraings": "hearings",
    "hearins": "hearings", "hering": "hearing", "hearng": "hearing", "hrng": "hearing",
    "nxt": "next", "wk": "week", "pls": "please", "plz": "please",
    "dedlines": "deadlines", "deadlnes": "deadlines", "deadines": "deadlines",
    "invoce": "invoice", "invioce": "invoice", "invocies": "invoices", "calender": "calendar",
}
_WORD_RE = re.compile(r"[a-z0-9]+")


# A handful of everyday Hindi time words, so "kal kya hai court mein" reads
# as tomorrow's calendar. Deliberately tiny: anything longer goes to the
# model, which reads mixed Hindi and English on its own.
_HINDI_PHRASES = (
    (re.compile(r"\bagle hafte\b|\bagla hafta\b"), "next week"),
    (re.compile(r"\bis hafte\b|\bis hafta\b"), "this week"),
    (re.compile(r"\bpichle hafte\b"), "last week"),
    (re.compile(r"\baaj\b"), "today"),
    (re.compile(r"\bparso\b|\bparson\b"), "day after tomorrow"),
    (re.compile(r"\bcourt mein\b|\bcourt me\b"), "in court"),
)
_KAL_RE = re.compile(r"\bkal\b")
_HINDI_PAST_RE = re.compile(r"\b(hua|hui|hue|tha|thi|gaya|gayi)\b")


def normalise_words(text: str) -> str:
    """`text` (already lower case) with shorthand words spelled out."""
    for pattern, replacement in _HINDI_PHRASES:
        text = pattern.sub(replacement, text)
    if _KAL_RE.search(text):
        # "kal" is both yesterday and tomorrow; a past-tense verb decides.
        text = _KAL_RE.sub("yesterday" if _HINDI_PAST_RE.search(text) else "tomorrow", text)
    return _WORD_RE.sub(lambda m: _WORD_FIXES.get(m.group(0), m.group(0)), text)


# ---------------------------------------------------------------------------
# Festivals ("what's on after Diwali")
# ---------------------------------------------------------------------------

FESTIVALS = {
    "diwali": (date(2025, 10, 20), date(2026, 11, 8), date(2027, 10, 29)),
    "deepavali": (date(2025, 10, 20), date(2026, 11, 8), date(2027, 10, 29)),
    "dussehra": (date(2025, 10, 2), date(2026, 10, 20), date(2027, 10, 9)),
    "dasara": (date(2025, 10, 2), date(2026, 10, 20), date(2027, 10, 9)),
    "holi": (date(2026, 3, 4), date(2027, 3, 22)),
    "christmas": (date(2025, 12, 25), date(2026, 12, 25), date(2027, 12, 25)),
    "new year": (date(2026, 1, 1), date(2027, 1, 1), date(2028, 1, 1)),
    "republic day": (date(2026, 1, 26), date(2027, 1, 26)),
    "independence day": (date(2026, 8, 15), date(2027, 8, 15)),
    "gandhi jayanti": (date(2025, 10, 2), date(2026, 10, 2), date(2027, 10, 2)),
    "sankranti": (date(2026, 1, 14), date(2027, 1, 14)),
    "pongal": (date(2026, 1, 14), date(2027, 1, 15)),
}
_FESTIVAL_RE = re.compile(
    r"\b(?P<rel>after|post|before|around|during|on|till|until)?\s*(?:the\s+)?(?P<name>"
    + "|".join(sorted(FESTIVALS, key=len, reverse=True))
    + r")\b"
)


def festival_period(text: str, today: date) -> Optional[tuple[date, date, str]]:
    """(date_from, date_to, note) for "after Diwali", "before Holi", "on
    Christmas": the festival's nearest date to today, then the week after or
    before it, or the day itself. The note states the date taken."""
    match = _FESTIVAL_RE.search(text)
    if not match:
        return None
    name, rel = match.group("name"), match.group("rel") or "on"
    day = min(FESTIVALS[name], key=lambda d: abs((d - today).days))
    if rel in ("after", "post"):
        span = (day + timedelta(days=1), day + timedelta(days=7))
    elif rel in ("before", "till", "until"):
        span = (day - timedelta(days=7), day - timedelta(days=1))
    elif rel == "around":
        span = (day - timedelta(days=3), day + timedelta(days=3))
    else:
        span = (day, day)
    tense = "was" if day < today else "is"
    return span[0], span[1], f"Taking {name.title()} as {day.strftime('%d %b %Y')} (it {tense} the nearest one)."


# ---------------------------------------------------------------------------
# Answers for what the assistant cannot do yet
# ---------------------------------------------------------------------------

LAW_QUESTION = (
    "I only answer from your own records in Case Intel, so I don't answer general law "
    "questions: a wrong section or citation is easy to miss and costly to rely on. "
    "Please check the bare act or a commentary for this."
)
FILING_DRAFT = (
    "I can't draft court filings such as {what}. From here I can start a **status memo**, a "
    "**client letter**, a **personal note** or a **list of dates** for one of your cases, "
    "for example: draft a list of dates for Rao vs State."
)
COMPARE_NOT_YET = (
    "I can't compare or rank your records yet; that is the next thing being built. "
    "For now, {suggestion}"
)
_COMPARE_SUGGESTIONS = {
    "billing": "ask **billing summary** to see every fee with its amount and status, or "
    "**billing report for this month** for totals.",
    "calendar": "ask **hearings this week** and **hearings next week** to see both counts.",
    "cases": "ask **overview** for case counts, or **cases report** for every active case with its next date.",
}
TASKS_NOT_YET = (
    "I can't add tasks from the chat yet. Add it on the case page under **Tasks**; "
    "it will then show in your deadlines and calendar."
)
MARK_PAID_NOT_YET = (
    "I can't mark invoices paid from the chat yet. Open **Billing** and use **Mark paid** on "
    "{what}."
)
BULK_NOT_YET = (
    "I add, change and send fees one at a time, so you can check each one before it is saved. "
    "Try: add a fee of 5000 for Rao vs State on 10 Nov. To see which hearings to bill, ask "
    "**hearings last week**."
)
EMAIL_NOT_YET = (
    "I can't email clients from here. The only thing I send is an invoice, and only after you confirm it."
)
BRIEF_NOT_YET = (
    "I can't write talking points for each hearing yet; that is being built. This report lists "
    "every hearing in the period with its case, court, purpose and cause-list position, so you "
    "can prepare from it."
)
ATTENTION_NOTE = (
    "These are your open tasks, earliest due first, so overdue ones lead. I can't yet weigh "
    "whole cases against each other; for cases with no next hearing date, ask **which cases have "
    "no next date**."
)

_LAW_REF_RE = re.compile(
    r"\b(?:section|sec\.?|s\.|article|art\.|order\s+[ivxl\d]+\s+rule|rule)\s*\d+[a-z]?\b"
)
_ACT_RE = re.compile(
    r"\b(ipc|crpc|cr\.p\.c|cpc|c\.p\.c|bns|bnss|bsa|ni act|negotiable instruments|evidence act|"
    r"constitution|limitation act|specific relief|contract act|transfer of property|"
    r"hindu marriage|ndps|pocso|it act|companies act|arbitration act)\b"
)
_ASKING_RE = re.compile(
    r"^(?:what|whats|what's|explain|meaning|define|definition|is|are|does|do|can|how|when|which|"
    r"tell me about|under what|why)\b"
)
_DEFINING_RE = re.compile(r"^(?:what|whats|what's|explain|meaning|define|definition|tell me about)\b")
_LAW_TOPIC_RE = re.compile(
    r"\b(case laws?|precedents?|landmark (?:case|judgment)s?|judgments? on|ratio decidendi|"
    r"bailable|non-bailable|cognizable|compoundable|punishment for|limitation period for|"
    r"ingredients of|essentials of|legal position)\b"
)
_MY_RECORDS_RE = re.compile(r"\b(my|our)\s+(cases?|matters?|hearings?|clients?|files?)\b")

_FILING_RE = re.compile(
    r"\b(bail application|bail petition|anticipatory bail|plaint|written statement|affidavit|"
    r"counter affidavit|counter|legal notice|reply notice|rejoinder|memo of appeal|appeal|"
    r"revision petition|writ petition|petition|vakalatnama|vakalat|interim application|"
    r"stay application|application|complaint|written submissions|submissions|notice)\b"
)
_DRAFT_VERB_RE = re.compile(r"\b(draft|write|prepare|compose|make|file)\b")
_SUPPORTED_DRAFT_RE = re.compile(
    r"\b(list of dates|synopsis of dates|dates and events|chronology|client letter|letter|"
    r"status memo|memo|memorandum|personal note|note to self|note)\b"
)

_COMPARE_RE = re.compile(
    r"\b(compar\w*|busier|busiest|rank\w*|oldest|newest|highest|lowest|biggest|largest|smallest|"
    r"cheapest|costliest|quite low|too low|too high|the most(?! recent)|the least|owes? (?:me )?(?:the )?most|"
    r"more than usual|less than usual|trend\w*)\b"
)
_TASK_RE = re.compile(
    r"^(?:(?:please|kindly)\s+)?(?:(?:can|could|would) you\s+)?"
    r"(?:(?:add|create|set|make|put)\s+(?:up\s+)?(?:a\s+|an\s+)?(?:new\s+)?(?:task|reminder|to-?do)\b|remind me\b)"
)
_MARK_PAID_RE = re.compile(r"\bmark\w*\b.*\b(paid|received|settled)\b|\b(paid|received|settled)\b.*\bmark\b")
_BULK_RE = re.compile(
    r"\b(?:bill|invoice|charge)\s+(?:for\s+)?(?:all|every|each)\b|"
    r"\b(?:all|every|each)\s+(?:of\s+)?(?:my\s+)?(?:the\s+)?hearings?\b.*\b(?:bill|fees?|invoices?)\b|"
    r"\b(?:add|create|generate|raise)\s+(?:fees?|invoices?)\s+for\s+(?:all|every|each)\b"
)
_EMAIL_CLIENT_RE = re.compile(
    r"\b(email|e-mail|mail|message|whatsapp|sms|write to|inform|notify)\b.*\b(clients?|parties|him|her|them)\b"
)
_INVOICE_WORD_RE = re.compile(r"\binvoices?\b|\b[a-z]{2,10}-\d{1,8}\b")
_INVOICE_NO_RE = re.compile(r"\b[a-z]{2,10}-\d{1,8}\b")


def _compare_domain(text: str) -> str:
    if re.search(r"\b(bill\w*|invoices?|fees?|paid|owes?|earn\w*|income|revenue|payments?)\b", text):
        return "billing"
    if re.search(r"\b(busy|busier|busiest|hearings?|week|days?|calendar|schedule)\b", text):
        return "calendar"
    return "cases"


def boundary_message(text: str) -> Optional[str]:
    """A fixed answer when `text` (normalised, lower case) asks for something
    the assistant cannot do, else None. Tasks, mark-paid, fees for many
    hearings and the comparisons in insights.compare_kind are cards and
    answers now, so they are not here."""
    if wants_task(text) or wants_mark_paid(text) or wants_bulk_fees(text):
        return None
    if not _MY_RECORDS_RE.search(text) and (
        _LAW_TOPIC_RE.search(text)
        or (_ASKING_RE.search(text) and _LAW_REF_RE.search(text))
        or (_DEFINING_RE.search(text) and _ACT_RE.search(text))
    ):
        return LAW_QUESTION
    filing = _FILING_RE.search(text)
    if filing and _DRAFT_VERB_RE.search(text) and not _SUPPORTED_DRAFT_RE.search(text):
        return FILING_DRAFT.format(what="a " + filing.group(0))
    if _EMAIL_CLIENT_RE.search(text) and not _INVOICE_WORD_RE.search(text) and not _SUPPORTED_DRAFT_RE.search(text):
        return EMAIL_NOT_YET
    if _COMPARE_RE.search(text):
        from .insights import compare_kind  # insights never imports this module

        if compare_kind(text) is None:
            return COMPARE_NOT_YET.format(suggestion=_COMPARE_SUGGESTIONS[_compare_domain(text)])
    return None


def wants_task(text: str) -> bool:
    return bool(_TASK_RE.search(text))


def wants_mark_paid(text: str) -> bool:
    return bool(_MARK_PAID_RE.search(text))


def wants_bulk_fees(text: str) -> bool:
    return bool(_BULK_RE.search(text))


_BULK_SEND_RE = re.compile(r"\b(send|email|e-mail|mail)\b.*\b(all|every|each|the unpaid|unsent|pending)\b.*\binvoices?\b")


def wants_bulk_send(text: str) -> bool:
    return bool(_BULK_SEND_RE.search(text)) and not _INVOICE_NO_RE.search(text)


def invoice_number_in(text: str) -> Optional[str]:
    """An invoice-number-shaped token ("INV-0001"), upper-cased, if any."""
    match = _INVOICE_NO_RE.search((text or "").lower())
    return match.group(0).upper() if match else None


def wants_comparison(text: str) -> bool:
    return bool(_COMPARE_RE.search(text))


# ---------------------------------------------------------------------------
# Two requests in one message
# ---------------------------------------------------------------------------

_SECOND_VERBS = (
    "email|e-mail|mail|send|add|create|draft|write|prepare|make|mark|bill|generate|delete|remove|"
    "change|update|list|show|tell|give|remind|inform|notify|book|raise|export|download|message"
)
_SPLIT_RE = re.compile(
    rf"\s*[,;]?\s+(?:and then|and also|and|then|also|plus)\s+(?=(?:please\s+)?(?:{_SECOND_VERBS})\b)"
)


_FORMAT_ONLY_RE = re.compile(r"\b(pdf|docx|word|document|doc|report|file|print\w*)\b")


def split_request(text: str) -> list[str]:
    """The separate requests in one message: "list my hearings this week and
    email the clients about them" -> ["list my hearings this week", "email the
    clients about them"]. Only splits before a verb, so "Rao and State" or
    "list of dates and events" stay whole. A part that only asks for the
    format ("and give it to me as a PDF") stays with the request before it,
    and a draft request is never split: the rest is its instructions."""
    if _DRAFT_VERB_RE.search(text) and _SUPPORTED_DRAFT_RE.search(text):
        return [text]
    parts: list[str] = []
    for part in (p.strip() for p in _SPLIT_RE.split(text)):
        if not part:
            continue
        if parts and _FORMAT_ONLY_RE.search(part):
            parts[-1] = f"{parts[-1]} and {part}"
        else:
            parts.append(part)
    return parts or [text]


def skipped_part_note(part: str) -> str:
    reason = boundary_message(part)
    head = f'I haven\'t done the other part of your message ("{part}").'
    return f"{head} {reason}" if reason else f"{head} Ask it on its own and I'll take it up."


# ---------------------------------------------------------------------------
# Phrasings routed to an existing read
# ---------------------------------------------------------------------------

_BRIEF_RE = re.compile(
    r"\b(talking points?|hearing (?:brief|prep\w*)|one[- ]page brief|points to argue|prep notes|"
    r"preparation notes|brief(?:ing)?s? (?:for|on) (?:my |the |each |all )?(?:hearings?|matters?|tomorrow|today|cases?)|"
    r"(?:hearings?|matters?)\b.*\bbrief(?:ing)?s?\b|brief(?:ing)?s?\b.*\b(?:hearings?|matters?))\b"
)
_EARNINGS_RE = re.compile(
    r"\b(earn\w*|income|revenue|collected|collections|received|made|make)\b.*\b(month|week|year|quarter|fy|today|so far|days?)\b|"
    r"\bhow much\b.*\b(earn\w*|income|revenue|collected|received|made|billed|paid)\b"
)
_ATTENTION_RE = re.compile(
    r"\b(needs? (?:my )?attention|urgent\w*|priorit\w*|"
    r"what(?:'s| is) pending|pending work|falling behind|neglect\w*|slipping)\b"
)
_FOCUS_RE = re.compile(
    r"\b(what should i (?:focus|work) on|focus on today|plan (?:for )?my day|how does my day look|"
    r"what(?:'s| is) on my plate today|start my day|my day today)\b"
)
_UPCOMING_RE = re.compile(
    r"\b(coming up|upcoming|ahead|lined up|on my plate|next few days|coming days|whats next|what's next)\b"
)
_NAMED_CASE_RE = re.compile(
    r"^(?:the\s+|my\s+)?([a-z][\w.&']*(?:\s+(?:vs?\.?|versus|[a-z][\w.&']*)){0,4}?)\s+(?:case|matter)\b"
)
_NOT_A_NAME = {
    "which", "what", "any", "all", "every", "how", "oldest", "this", "that", "each", "a", "one",
    "new", "next", "last", "latest", "open", "closed", "pending", "active", "my", "the", "show",
    "list", "give", "tell", "is", "are", "add", "draft",
}
_CASE_QUESTION_RE = re.compile(r"\b(next (?:date|hearing)|status|stage|last order|what(?:'s| is) happening|update)\b")


def wants_hearing_brief(text: str) -> bool:
    return bool(_BRIEF_RE.search(text))


def wants_earnings(text: str) -> bool:
    return bool(_EARNINGS_RE.search(text))


def wants_attention(text: str) -> bool:
    return bool(_ATTENTION_RE.search(text))


def wants_focus(text: str) -> bool:
    return bool(_FOCUS_RE.search(text))


def wants_upcoming(text: str) -> bool:
    return bool(_UPCOMING_RE.search(text))


def named_case_text(text: str) -> Optional[str]:
    """"rao case next date" -> "rao": a case named the way people say it,
    only when the question asks about that case (next date, status...)."""
    if not _CASE_QUESTION_RE.search(text):
        return None
    match = _NAMED_CASE_RE.search(text)
    if not match:
        return None
    name = match.group(1).strip()
    if name.split()[0] in _NOT_A_NAME or len(name) < 3:
        return None
    return name
