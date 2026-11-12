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

from core.models import Case
from core.services.ai_service_factory import get_llm_client
from core.services.practice_assistant import actions, answers, billing, parsing, reads, reports
from core.services.practice_assistant.contracts import (
    DEFAULT_RANGE_DAYS,
    HARD_ROW_CAP,
    INTENTS,
    MAX_RANGE_DAYS,
    PAGE_SIZE,
    REPORT_KINDS,
    SCOPE_PERSONAL,
)

logger = logging.getLogger(__name__)

# The billing intents run only while settings.PRACTICE_INVOICE_ACTIONS_ENABLED
# is on (checked per request), the draft intent only while
# settings.CASE_DRAFTING_ENABLED is. Off, a turn classified as one is told so
# and never gets a card. Nothing in this module writes: no mail is sent, no
# invoice generated, no fee or draft created. A `propose_*` intent builds an
# action card from the owner's rows; the advocate's click calls the existing
# endpoint (see practice_assistant/actions.py).
READ_INTENTS = ("overview", "calendar", "open_deadlines", "missing_next_date", "case_facts")
BILLING_INTENTS = ("billing_summary", "propose_invoice_send")
FEE_INTENTS = actions.FEE_ACTION_INTENTS
GATED_BILLING_INTENTS = BILLING_INTENTS + FEE_INTENTS

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


def drafting_enabled() -> bool:
    return bool(getattr(settings, "CASE_DRAFTING_ENABLED", False))


def assistant_enabled() -> bool:
    return bool(getattr(settings, "PRACTICE_ASSISTANT_ENABLED", False))


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

     -3. "draft / write / prepare ... a memo, note, letter or list of dates"
                                                          -> propose_draft
     -2. "report", "export", "as a PDF" (no case selected) -> practice_report
     -1. a command that starts with delete / change / generate invoice / add
         and names a fee, charge or invoice               -> a propose_fee_* or
                                                             propose_invoice_generate
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
    if parsing.parse_draft_request(text):
        return "propose_draft", {}
    if case_id is None and parsing.wants_report(text):
        return "practice_report", {}
    mutation = parsing.parse_fee_mutation(text)
    if mutation:
        return mutation, {}
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
    '"case_text": a case number, CNR or party name copied from the question, or null, '
    '"subtype": "status_memo", "personal_note", "client_letter" or "list_of_dates" for a draft, else null, '
    '"report_kind": "billing", "hearings", "cases" or "deadlines" for a report, else null}. '
    "overview = counts across all cases. calendar = hearings, tasks and events on dates "
    "(give the dates, at most 31 days). open_deadlines = open tasks and due dates. "
    "missing_next_date = active cases with no next hearing date. case_facts = anything about "
    "one named case (set case_text). billing_summary and propose_invoice_send = fees and invoices. "
    "propose_fee_create, propose_fee_update, propose_invoice_generate and propose_fee_delete = a "
    "request to add, change, invoice or delete a fee (set case_text if a case is named). "
    "practice_report = a request for a downloadable report (set report_kind). "
    "propose_draft = a request to start a memo, note, letter or list of dates for one case "
    "(set subtype and case_text). "
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
            max_tokens=160,
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
    case_text = data.get("case_text")
    case_text = case_text.strip()[:MAX_CASE_TEXT] if isinstance(case_text, str) else ""
    if intent in FEE_INTENTS:
        return {"intent": intent, "args": {"case_text": case_text} if case_text else {}}
    if intent == "practice_report":
        kind = data.get("report_kind")
        return {"intent": intent, "args": {"report_kind": kind} if kind in REPORT_KINDS else {}}
    if intent == "propose_draft":
        subtype = data.get("subtype")
        args = {"subtype": subtype} if subtype in actions.DRAFT_SUBTYPES else {}
        if case_text:
            args["case_text"] = case_text
        return {"intent": intent, "args": args}
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
        "report": None,
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


def _case_summary(case: Case) -> dict:
    return {"cases": [{"id": case.id, "title": case.title}]}


def _resolve_case(state: dict, *, no_text_message: str = answers.CASE_TEXT_NEEDED) -> tuple[Optional[Case], Optional[dict]]:
    """The one case a command is about, as (case, None), or (None, a state
    update that asks the advocate). A verified `case_id` (the chooser's pick)
    is the case. Text from the question or the model is only ever searched
    for under the owner and offered as a chooser; it becomes the case itself
    only when the advocate typed that case's exact number or CNR."""
    owner, query, intent = state["owner"], state["query"], state["intent"]
    case_id = state.get("case_id")
    if case_id is not None:
        case = Case.objects.filter(id=case_id, owner=owner).first()
        if case is None:
            return None, _clarify(answers.CASE_NOT_FOUND, intent)
        return case, None

    model_text = state["args"].get("case_text")
    needles = ([model_text] if model_text else []) + parsing.case_text_needles(query)
    if not needles:
        return None, _clarify(no_text_message, intent)
    for needle in needles:
        candidates = reads.resolve_case_candidates(owner=owner, text=needle, limit=CASE_CANDIDATE_LIMIT)
        if candidates:
            break
    else:
        return None, _clarify(answers.CASE_NOT_FOUND, intent)
    if len(candidates) == 1:
        case = Case.objects.filter(id=candidates[0]["id"], owner=owner).first()
        wanted = _squash(needle)
        if (
            case is not None
            and wanted
            and wanted in _squash(query)
            and wanted in (_squash(case.case_number), _squash(case.cnr_number))
        ):
            return case, None
    return None, {**_clarify(answers.CHOOSE_CASE, intent), "case_candidates": candidates}


def _read_fee_action(state: dict) -> dict:
    """A card for adding, changing, invoicing or deleting one fee. Every field
    is read from the owner's rows or from the advocate's own words."""
    intent, owner, now, query = state["intent"], state["owner"], state["now"], state["query"]
    if intent == "propose_fee_create":
        case, ask = _resolve_case(state)
        if ask:
            return ask
        return {
            "summary": _case_summary(case),
            "action_card": actions.build_create_card(owner=owner, case=case, query=query, now=now),
        }

    named = billing.named_fees(owner=owner, text=query, case_id=state.get("case_id"))
    if len(named) > 1:
        return _clarify(answers.MANY_INVOICES, intent)
    if named:
        fee = named[0]
    else:
        case, ask = _resolve_case(state, no_text_message=answers.WHICH_FEE)
        if ask:
            return ask
        fee = actions.select_fee(intent, billing.case_fees(owner=owner, case_id=case.id))
        if fee is None:
            return _clarify(answers.no_fees_for_case(case.title), intent)

    if intent == "propose_fee_update":
        proposed = actions.proposed_changes(fee, query)
        if not proposed:
            return _clarify(answers.NOTHING_TO_CHANGE, intent)
        card = actions.build_update_card(fee=fee, proposed=proposed)
    elif intent == "propose_invoice_generate":
        card = actions.build_generate_card(fee=fee)
    else:
        card = actions.build_delete_card(fee=fee)
    rows = billing.candidate_rows([fee])
    summary = {"fee": rows[0], "cases": billing.case_list(rows)}
    return {"summary": summary, "action_card": card}


def _read_draft(state: dict) -> dict:
    intent, query = state["intent"], state["query"]
    subtype = state["args"].get("subtype") or parsing.parse_draft_request(query)
    if subtype not in actions.DRAFT_SUBTYPES:
        return _clarify(answers.DRAFT_KIND_NEEDED, intent)
    case, ask = _resolve_case(state)
    if ask:
        return ask
    return {
        "summary": _case_summary(case),
        "action_card": actions.build_draft_card(case=case, subtype=subtype, query=query),
    }


def _read_report(state: dict) -> dict:
    """A report card for a downloadable file (the file itself is the report
    endpoint's job). The data is built once here only to count its rows."""
    intent, today = state["intent"], state["now"].date()
    kind = state["args"].get("report_kind") or parsing.parse_report_kind(state["query"])
    if kind not in REPORT_KINDS:
        return _clarify(answers.REPORT_KIND_NEEDED, intent)
    period = parsing.parse_period(state["query"], today=today)
    try:
        report = reports.build_report(
            owner=state["owner"],
            kind=kind,
            date_from=period[0] if period else None,
            date_to=period[1] if period else None,
            now=state["now"],
        )
    except reports.ReportError as exc:
        return _clarify(str(exc), intent)
    summary = {
        "kind": report["kind"],
        "title": report["title"],
        "period_text": report["period_text"],
        "row_count": report["row_count"],
        "totals": reports.totals_for_answer(report),
    }
    return {"summary": summary, "report": reports.report_card(report)}


def run_read(state: dict) -> dict:
    """The typed read for the chosen intent, under the request's owner."""
    if state["answer"]:
        return {}
    intent = state["intent"]
    owner, now = state["owner"], state["now"]
    if intent in GATED_BILLING_INTENTS:
        if not invoice_actions_enabled():
            return _clarify(
                answers.FEE_ACTIONS_OFF if intent in FEE_INTENTS else answers.BILLING_NOT_AVAILABLE, intent
            )
        return _read_fee_action(state) if intent in FEE_INTENTS else _read_billing(state)
    if intent == "propose_draft":
        if not drafting_enabled():
            return _clarify(answers.DRAFTING_OFF, intent)
        return _read_draft(state)
    if intent == "practice_report":
        if not assistant_enabled():
            return _clarify(answers.REPORTS_OFF, intent)
        return _read_report(state)
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
    elif state["intent"] in FEE_INTENTS:
        text, sources = answers.fee_action_answer(state["action_card"], state["summary"])
    elif state["intent"] == "propose_draft":
        text, sources = answers.draft_answer(state["action_card"])
    elif state["intent"] == "practice_report":
        text, sources = answers.report_answer(state["summary"])
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
