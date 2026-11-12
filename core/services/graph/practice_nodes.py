"""Nodes of the practice-assistant graph (see practice_graph.py).

    validate_scope -> select_intent -> run_read -> present -> validate_references

What the model may and may not do here:

  - At most ONE model call per turn, and only when the deterministic rules in
    `route_deterministic` cannot place the question. It is a single attempt
    with the short HyDE timeout (settings.AI_HYDE_TIMEOUT_SECONDS).
  - The model only proposes an intent from the closed enum, a date range and
    a piece of case text. Each is validated here. It never supplies an owner,
    an id, SQL or ORM, and its text is never turned into a case id: case text
    goes through reads.resolve_case_candidates under the request's owner and
    comes back as a chooser.
  - The answer text is built in answers.py from the read result alone.

Logging is metadata only: never the question or the answer.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import logging
import re
from datetime import date, timedelta
from typing import Optional

from django.conf import settings

from core.services.ai_service_factory import get_llm_client
from core.services.practice_assistant import answers, billing, reads
from core.services.practice_assistant.contracts import (
    DEFAULT_RANGE_DAYS,
    HARD_ROW_CAP,
    INTENTS,
    MAX_RANGE_DAYS,
    PAGE_SIZE,
    SCOPE_PERSONAL,
)

logger = logging.getLogger(__name__)

# The billing intents run only while settings.PRACTICE_INVOICE_ACTIONS_ENABLED
# is on (checked per request). Off, a turn classified as one is told so and
# never gets an action card. They only read: nothing in this module sends mail,
# generates an invoice or changes a fee.
READ_INTENTS = ("overview", "calendar", "open_deadlines", "missing_next_date", "case_facts")
BILLING_INTENTS = ("billing_summary", "propose_invoice_send")

# The whole model budget of one turn: the intent classifier, once.
MAX_LLM_CALLS_PER_TURN = 1

CASE_CANDIDATE_LIMIT = 5
MAX_CASE_TEXT = 200

STATUS_ANSWER = "answer"
STATUS_CLARIFY = "needs_clarification"

# The dashboard's four suggested questions (frontend-next
# components/dashboard/practice/practice-assistant-panel.tsx), normalised.
CHIP_INTENTS = {
    "give me an overview of my practice": "overview",
    "what is on my calendar this week": "calendar",
    "what deadlines are open": "open_deadlines",
    "which cases have no next date": "missing_next_date",
}

_BILLING_RE = re.compile(r"\b(invoices?|invoiced|billing|bills?|fees?|payments?|unpaid|paid)\b")
_SEND_RE = re.compile(r"\b(send|email|e-mail|mail)\b")
_MISSING_RE = re.compile(
    r"\b(no|without(?: a| any)?|missing)\s+"
    r"(next\s+(?:hearing\s+)?dates?|next\s+hearings?|(?:hearing\s+)?dates?)\b"
)
_DEADLINE_RE = re.compile(r"\b(deadlines?|overdue|tasks?|to-?dos?|due)\b")
_CALENDAR_RE = re.compile(
    r"\b(calendar|schedule|agenda|hearings?|today|tomorrow|this week|next week|listed)\b"
)
_DAY_RE = re.compile(
    r"(\bwhat(?:'s| is) on\b|\b(this day|that day|selected day|calendar|schedule|agenda|hearings?|listed|happening)\b)"
)
_OVERVIEW_RE = re.compile(r"\b(overview|portfolio|how many cases|my practice|summary)\b")
# "Rao vs State": a question about one matter, which keyword rules cannot place.
_PARTIES_RE = re.compile(r"\b(v|vs|versus)\b")
_ISO_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_CNR_RE = re.compile(r"\b(?=[A-Za-z0-9]*\d)[A-Za-z]{4}[A-Za-z0-9]{12}\b")
_CASE_NUMBER_RE = re.compile(r"\b[A-Za-z][A-Za-z.()]*\s?[/.\-]?\s?\d+\s?/\s?\d{4}\b")


def _normalise(text: str) -> str:
    return " ".join((text or "").lower().split()).rstrip("?.! ")


def _squash(text: Optional[str]) -> str:
    return "".join((text or "").split()).casefold()


def _parse_day(value) -> Optional[date]:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _default_week(today: date) -> tuple[date, date]:
    return today, today + timedelta(days=DEFAULT_RANGE_DAYS - 1)


def _range_ok(date_from: date, date_to: date) -> bool:
    return date_from <= date_to and (date_to - date_from).days + 1 <= MAX_RANGE_DAYS


def _calendar_args(date_from: date, date_to: date) -> dict:
    return {"date_from": date_from, "date_to": date_to}


# ---------------------------------------------------------------------------
# Deterministic routing (no model)
# ---------------------------------------------------------------------------


def invoice_actions_enabled() -> bool:
    return bool(getattr(settings, "PRACTICE_INVOICE_ACTIONS_ENABLED", False))


def route_deterministic(
    query: str,
    *,
    selected_day: Optional[date],
    case_id: Optional[int],
    today: date,
    billing_enabled: bool = False,
) -> Optional[tuple[str, dict]]:
    """(intent, args) when the rules below place the question, else None.
    First match wins:

      0. billing words, only when `billing_enabled`       -> a billing intent
         (a `case_id` then narrows it instead of selecting case_facts)
      1. a verified `case_id` came with the request      -> case_facts
      2. the text is one of the four suggested questions  -> that intent
         (the calendar one covers India today + 6 days)
      3. `selected_day` came with the request and the text is about a day
         ("what is on ...", calendar, schedule, hearings) -> calendar, that day
      4. billing words (invoice, bill, fee, payment)      -> a billing intent
      5. "no / without / missing (next) (hearing) date"   -> missing_next_date
      6. a CNR or a case number ("OS/12/2026")            -> case_facts, that text
      7. the text names parties ("X vs Y")                -> undecided
      8. deadline, overdue, task, due                     -> open_deadlines
      9. calendar, schedule, hearings, today, tomorrow, this/next week, or a
         YYYY-MM-DD date                                  -> calendar
     10. overview, portfolio, "how many cases"            -> overview
    """
    text = _normalise(query)
    if billing_enabled and _BILLING_RE.search(text):
        return ("propose_invoice_send" if _SEND_RE.search(text) else "billing_summary"), {}
    if case_id is not None:
        return "case_facts", {}
    if text in CHIP_INTENTS:
        intent = CHIP_INTENTS[text]
        return intent, _calendar_args(*_default_week(today)) if intent == "calendar" else {}
    billing = bool(_BILLING_RE.search(text))
    if selected_day is not None and not billing and _DAY_RE.search(text):
        return "calendar", _calendar_args(selected_day, selected_day)
    if billing:
        return ("propose_invoice_send" if _SEND_RE.search(text) else "billing_summary"), {}
    if _MISSING_RE.search(text):
        return "missing_next_date", {}
    token = _CNR_RE.search(query) or _CASE_NUMBER_RE.search(query)
    if token:
        return "case_facts", {"case_text": token.group(0).strip()}
    if _PARTIES_RE.search(text):
        return None
    if _DEADLINE_RE.search(text):
        return "open_deadlines", {}
    days = [d for d in (_parse_day(m) for m in _ISO_DATE_RE.findall(text)) if d]
    if days or _CALENDAR_RE.search(text):
        if days:
            date_from, date_to = min(days), max(days)
        elif "tomorrow" in text:
            date_from = date_to = today + timedelta(days=1)
        elif "today" in text:
            date_from = date_to = today
        elif "next week" in text:
            date_from = today + timedelta(days=DEFAULT_RANGE_DAYS)
            date_to = date_from + timedelta(days=DEFAULT_RANGE_DAYS - 1)
        else:
            date_from, date_to = _default_week(today)
        return "calendar", _calendar_args(date_from, date_to)
    if _OVERVIEW_RE.search(text):
        return "overview", {}
    return None


# ---------------------------------------------------------------------------
# The one model call: classify free text
# ---------------------------------------------------------------------------

_CLASSIFIER_SYSTEM = (
    "You route one question from an Indian advocate about their own practice records. "
    "Reply with a single JSON object and nothing else: "
    '{"intent": one of ' + ", ".join(f'"{name}"' for name in INTENTS) + ', or "none", '
    '"date_from": "YYYY-MM-DD" or null, "date_to": "YYYY-MM-DD" or null, '
    '"case_text": a case number, CNR or party name copied from the question, or null}. '
    "overview = counts across all cases. calendar = hearings, tasks and events on dates "
    "(give the dates, at most 31 days). open_deadlines = open tasks and due dates. "
    "missing_next_date = active cases with no next hearing date. case_facts = anything about "
    "one named case (set case_text). billing_summary and propose_invoice_send = fees and invoices. "
    'Use "none" when the question is about anything else. Never answer the question.'
)


def _classify_with_model(query: str, today: date) -> Optional[dict]:
    """One bounded attempt. None on any failure or unusable output."""
    budget = getattr(settings, "AI_HYDE_TIMEOUT_SECONDS", 10)
    # The per-call timeout below bounds the OpenAI/Groq client, but the Ollama
    # client ignores it and waits up to its own 120 s. The wall-clock wait on
    # the future bounds every provider: a slow model costs this turn a
    # clarification, never a request thread held for minutes.
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        llm = get_llm_client()
        future = pool.submit(
            llm.generate,
            [
                {"role": "system", "content": _CLASSIFIER_SYSTEM},
                {"role": "user", "content": f"Today (India): {today.isoformat()}\nQuestion: {query}"},
            ],
            temperature=0,
            max_tokens=120,
            # The HyDE mechanism: a per-call timeout makes this a single
            # attempt of that length, no retries (LLMClient._client_for).
            timeout=budget,
        )
        raw = future.result(timeout=budget + 2)
    except Exception as exc:
        pool.shutdown(wait=False, cancel_futures=True)
        logger.warning("Practice intent classifier failed: %s", type(exc).__name__)
        return None
    pool.shutdown(wait=False)
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        logger.warning("Practice intent classifier returned unparseable output.")
        return None
    return data if isinstance(data, dict) else None


def _clarify(message: str, intent: Optional[str] = None) -> dict:
    return {"intent": intent, "status": STATUS_CLARIFY, "answer": message}


def _from_model(data: dict, *, selected_day: Optional[date], today: date) -> dict:
    """Validate a classifier proposal into a state update. Only the enum, two
    dates and a bounded piece of case text are read; anything else is ignored."""
    intent = data.get("intent")
    if intent in BILLING_INTENTS:
        return {"intent": intent, "args": {}}
    if intent not in READ_INTENTS:
        return _clarify(answers.FALLBACK_CLARIFICATION)
    if intent == "calendar":
        raw_from, raw_to = data.get("date_from"), data.get("date_to")
        date_from, date_to = _parse_day(raw_from), _parse_day(raw_to)
        if (raw_from and not date_from) or (raw_to and not date_to):
            return _clarify(answers.FALLBACK_CLARIFICATION)
        if date_from is None and date_to is None:
            date_from, date_to = (selected_day, selected_day) if selected_day else _default_week(today)
        else:
            date_from = date_from or date_to
            date_to = date_to or date_from
        if not _range_ok(date_from, date_to):
            return _clarify(answers.RANGE_TOO_LONG, intent)
        return {"intent": intent, "args": _calendar_args(date_from, date_to)}
    if intent == "case_facts":
        case_text = data.get("case_text")
        if not isinstance(case_text, str) or not case_text.strip():
            return _clarify(answers.CASE_TEXT_NEEDED, intent)
        return {"intent": intent, "args": {"case_text": case_text.strip()[:MAX_CASE_TEXT]}}
    return {"intent": intent, "args": {}}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def validate_scope(state: dict) -> dict:
    """The server set these; a bad value is a bug in the caller, not a turn."""
    if state.get("scope") != SCOPE_PERSONAL:
        raise ValueError("The practice assistant only runs in the personal scope.")
    if state.get("owner") is None or not getattr(state["owner"], "pk", None):
        raise ValueError("The practice assistant needs the requesting owner.")
    if state["now"].tzinfo is None:
        raise ValueError("now must be an aware datetime.")
    return {
        "intent": None,
        "args": {},
        "routed_by": "none",
        "llm_calls": 0,
        "status": STATUS_ANSWER,
        "answer": "",
        "summary": None,
        "sources": [],
        "case_candidates": [],
        "action_card": None,
    }


def select_intent(state: dict) -> dict:
    today = state["now"].date()
    routed = route_deterministic(
        state["query"],
        selected_day=state.get("selected_day"),
        case_id=state.get("case_id"),
        today=today,
        billing_enabled=invoice_actions_enabled(),
    )
    if routed is not None:
        intent, args = routed
        if intent == "calendar" and not _range_ok(args["date_from"], args["date_to"]):
            return {"routed_by": "rule", **_clarify(answers.RANGE_TOO_LONG, intent)}
        return {"intent": intent, "args": args, "routed_by": "rule"}

    proposal = _classify_with_model(state["query"], today)
    update = {"routed_by": "llm", "llm_calls": 1}
    if proposal is None:
        return {**update, **_clarify(answers.FALLBACK_CLARIFICATION)}
    return {**update, **_from_model(proposal, selected_day=state.get("selected_day"), today=today)}


def _is_exact_case_match(text: str, query: str, candidate: dict, facts: dict) -> bool:
    """The advocate typed this case's exact number or CNR themselves."""
    wanted = _squash(text)
    if not wanted or wanted not in _squash(query):
        return False  # model text that is not in the question never picks a case
    case = facts["case"]
    return wanted in (_squash(candidate["case_number"]), _squash(case["case_number"]), _squash(case["cnr_number"]))


def _read_case(state: dict) -> dict:
    owner, now = state["owner"], state["now"]
    case_id = state.get("case_id")
    if case_id is not None:
        facts = reads.case_facts(owner=owner, case_id=case_id, now=now)
        if facts is None:
            return _clarify(answers.CASE_NOT_FOUND, "case_facts")
        return {"summary": facts}

    text = state["args"].get("case_text") or ""
    candidates = reads.resolve_case_candidates(owner=owner, text=text, limit=CASE_CANDIDATE_LIMIT)
    if not candidates:
        return _clarify(answers.CASE_NOT_FOUND, "case_facts")
    if len(candidates) == 1:
        facts = reads.case_facts(owner=owner, case_id=candidates[0]["id"], now=now)
        if facts is not None and _is_exact_case_match(text, state["query"], candidates[0], facts):
            return {"summary": facts}
    # Anything short of the advocate's own exact case number / CNR is a
    # chooser, even with a single match: text never becomes a case id.
    return {**_clarify(answers.CHOOSE_CASE, "case_facts"), "case_candidates": candidates}


MAX_SEND_CANDIDATES = 100
SEND_ROWS = 25


def _read_billing(state: dict) -> dict:
    """Typed billing reads under the request's owner. The fee behind a card is
    always one of the owner's rows; text from the model never reaches here."""
    owner, now = state["owner"], state["now"]
    case_id = state.get("case_id")
    if state["intent"] == "billing_summary":
        return {
            "summary": billing.billing_summary(owner=owner, scope=state["scope"], case_id=case_id, now=now)
        }
    fees = billing.invoice_send_candidates(
        owner=owner, scope=state["scope"], case_id=case_id, text=state["query"]
    )[:MAX_SEND_CANDIDATES]
    rows = billing.candidate_rows(fees[:SEND_ROWS])
    summary = {
        "candidates": rows,
        "cases": billing.case_list(rows),
        "total": len(fees),
        "as_of": now.isoformat(),
        "timezone": "Asia/Kolkata",
    }
    card = billing.build_send_card(owner=owner, fee=fees[0]) if len(fees) == 1 else None
    return {"summary": summary, "action_card": card}


def run_read(state: dict) -> dict:
    """The typed read for the chosen intent, under the request's owner."""
    if state["answer"]:
        return {}
    intent = state["intent"]
    owner, now = state["owner"], state["now"]
    if intent in BILLING_INTENTS:
        if not invoice_actions_enabled():
            return _clarify(answers.BILLING_NOT_AVAILABLE, intent)
        return _read_billing(state)
    if intent == "overview":
        return {"summary": reads.portfolio_snapshot(owner=owner, page=1, page_size=PAGE_SIZE, now=now)}
    if intent == "calendar":
        args = state["args"]
        return {
            "summary": reads.calendar_window(
                owner=owner, date_from=args["date_from"], date_to=args["date_to"], now=now
            )
        }
    if intent == "open_deadlines":
        return {"summary": reads.open_deadlines(owner=owner, limit=PAGE_SIZE, now=now)}
    if intent == "missing_next_date":
        snapshot = reads.portfolio_snapshot(owner=owner, page=1, page_size=HARD_ROW_CAP, now=now)
        return {"summary": answers.missing_next_date_summary(snapshot, reads.INACTIVE_CASE_STATUSES)}
    if intent == "case_facts":
        return _read_case(state)
    raise ValueError(f"No read for intent {intent!r}.")


_PRESENTERS = {
    "overview": answers.overview_answer,
    "calendar": answers.calendar_answer,
    "open_deadlines": answers.open_deadlines_answer,
    "missing_next_date": answers.missing_next_date_answer,
    "case_facts": answers.case_facts_answer,
}


def present(state: dict) -> dict:
    """Deterministic text from the read result. No synthesis in this wave."""
    if state["answer"] or state["summary"] is None:
        return {}
    if state["intent"] == "billing_summary":
        text, sources = answers.billing_summary_answer(state["summary"])
    elif state["intent"] == "propose_invoice_send":
        card = state.get("action_card")
        text, sources = answers.invoice_send_answer(state["summary"], card)
        if card is None and state["summary"]["total"] > 1:
            return {"answer": text, "sources": sources, "status": STATUS_CLARIFY}
    else:
        text, sources = _PRESENTERS[state["intent"]](state["summary"])
    return {"answer": text, "sources": sources, "status": STATUS_ANSWER}


def validate_references(state: dict) -> dict:
    """Keep only sources that are References of the read result."""
    allowed = answers.allowed_references(state["summary"]) if state["summary"] else {}
    kept = [
        ref
        for ref in state["sources"]
        if isinstance(ref, dict) and allowed.get((ref.get("kind"), ref.get("id"))) == ref
    ]
    dropped = len(state["sources"]) - len(kept)
    if dropped:
        logger.warning("Practice turn dropped %d source(s) not in the read result.", dropped)
    return {"sources": kept[: answers.MAX_SOURCES]}
