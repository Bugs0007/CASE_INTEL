"""Generate and persist one order's Overview summary.

Called exactly once per order, from the process_jobs worker after the
order's document finishes extraction/OCR (see the document branch of
core/management/commands/process_jobs.py). Never called from a
serializer, a view, or anything on the page-view path: the whole point is
that reading a case page costs nothing.

Every order logs the route it took at INFO with a reason, so the share of
orders that actually reach the LLM is visible in the worker log without
instrumentation.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from django.utils import timezone

from core.models import CourtOrder

from .prompt import build_messages, build_retry_messages
from .routing import (
    ROUTE_ROUTINE,
    ROUTE_SHORT,
    ROUTE_UNREADABLE,
    classify_order_text,
)

logger = logging.getLogger(__name__)

MAX_LLM_ATTEMPTS = 2  # first attempt + one retry on a parse failure

# What the free paths write instead of a generated summary.
UNREADABLE_TEXT = (
    "This order could not be read automatically -- the PDF carries no "
    "extractable text (it is a scan, and OCR produced nothing usable). "
    "Open the order to read it."
)
ROUTINE_TEXT = (
    "No directions were issued -- the order records a routine adjournment "
    "or re-listing of the matter."
)
SHORT_TEXT = (
    "No directions were issued -- the order is a brief procedural note with "
    "no substantive content."
)


class OrderSummaryError(Exception):
    """Raised when summarisation fails in a way worth surfacing."""


def summarize_court_order(order: CourtOrder, *, force: bool = False) -> CourtOrder:
    """Summarise `order` and persist the result on the row.

    Idempotent by default: an order that already has a resolved summary
    is left alone, because this runs at ingest and the result is cached
    forever. `force=True` re-runs it (a prompt change, a failed order
    being retried by hand) and is the ONLY way to spend a second LLM call
    on the same order.
    """
    if not force and order.summary_status not in (
        CourtOrder.SUMMARY_PENDING,
        CourtOrder.SUMMARY_FAILED,
    ):
        logger.debug(
            "Order %d already summarised (%s) -- skipping.", order.id, order.summary_status
        )
        return order

    text = _order_text(order)
    result = summarize_order_text(order, text)
    return _persist(order, result)


def summarize_order_text(order: CourtOrder, text: str) -> dict:
    """Route `text` and produce a summary payload. Persists nothing.

    Split out from summarize_court_order so the routing and JSON-retry
    behaviour is testable without touching the DB or the ingest pipeline.
    """
    route, reason = classify_order_text(text)

    if route == ROUTE_UNREADABLE:
        logger.info(
            "Order summary route=UNREADABLE order=%s (%s) -- no LLM call.",
            getattr(order, "id", "?"),
            reason,
        )
        return _templated(CourtOrder.SUMMARY_UNREADABLE, route, UNREADABLE_TEXT)

    if route in (ROUTE_SHORT, ROUTE_ROUTINE):
        logger.info(
            "Order summary route=%s order=%s (%s) -- no LLM call.",
            route.upper(),
            getattr(order, "id", "?"),
            reason,
        )
        body = ROUTINE_TEXT if route == ROUTE_ROUTINE else SHORT_TEXT
        payload = _templated(CourtOrder.SUMMARY_NO_DIRECTIONS, route, body)
        payload["is_routine_adjournment"] = route == ROUTE_ROUTINE
        return payload

    logger.info(
        "Order summary route=LLM order=%s (%s) -- calling the model.",
        getattr(order, "id", "?"),
        reason,
    )
    return _summarize_with_llm(order, text, route)


def _summarize_with_llm(order: CourtOrder, text: str, route: str) -> dict:
    from core.services.ai_service_factory import get_llm_client

    client = get_llm_client()
    messages = build_messages(order, text)
    last_error = ""
    raw = ""

    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        try:
            raw = client.generate_with_json(messages, temperature=0)
        except Exception as exc:  # noqa: BLE001 -- provider/network failures
            # A transport failure is not a parse failure: retrying the
            # same call is what the provider clients already do
            # internally, so fail visibly rather than burning the one
            # retry that exists for malformed JSON.
            logger.exception("Order %s: LLM call failed on attempt %d.", order.id, attempt)
            return _failed(route, f"LLM call failed: {exc}", llm_calls=attempt)

        try:
            data = _validate_payload(raw)
        except ValueError as exc:
            last_error = str(exc)
            logger.warning(
                "Order %s: LLM returned unusable JSON on attempt %d/%d (%s).",
                order.id,
                attempt,
                MAX_LLM_ATTEMPTS,
                last_error,
            )
            if attempt < MAX_LLM_ATTEMPTS:
                messages = build_retry_messages(order, text, raw)
                continue
            break
        else:
            logger.info(
                "Order %s summarised in %d LLM call(s).", order.id, attempt
            )
            return {
                "status": CourtOrder.SUMMARY_SUMMARIZED,
                "route": route,
                "what_happened": data["what_happened"],
                "petitioner_directions": data["petitioner_directions"],
                "respondent_directions": data["respondent_directions"],
                "next_date": data["next_date"],
                "next_date_purpose": data["next_date_purpose"],
                "is_routine_adjournment": data["is_routine_adjournment"],
                "error": "",
                "llm_calls": attempt,
            }

    return _failed(
        route,
        f"The model did not return valid JSON after {MAX_LLM_ATTEMPTS} attempts: {last_error}",
        llm_calls=MAX_LLM_ATTEMPTS,
    )


def _validate_payload(raw: str) -> dict:
    """Parse and type-check the model's reply.

    Raises ValueError with a specific reason on anything unusable -- the
    caller turns the first one into a retry and the second into a visible
    FAILED status.
    """
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty response")

    # Some providers still wrap JSON in a code fence despite the
    # json_object response format; unwrap rather than burning the retry.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON ({exc.msg})") from exc

    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object, got {type(data).__name__}")

    what_happened = data.get("what_happened")
    if not isinstance(what_happened, str) or not what_happened.strip():
        raise ValueError("'what_happened' missing or not a non-empty string")

    return {
        "what_happened": what_happened.strip(),
        "petitioner_directions": _string_list(data.get("petitioner_directions"), "petitioner_directions"),
        "respondent_directions": _string_list(data.get("respondent_directions"), "respondent_directions"),
        "next_date": _parse_date(data.get("next_date")),
        "next_date_purpose": _optional_str(data.get("next_date_purpose")),
        "is_routine_adjournment": bool(data.get("is_routine_adjournment", False)),
    }


def _string_list(value, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"'{field_name}' must be a list")
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_str(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _parse_date(value) -> date | None:
    """The model is told to emit YYYY-MM-DD or null.

    A malformed date is dropped rather than failing the whole summary:
    losing the next date is a much smaller loss than losing the
    directions, and the order itself remains one click away.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        logger.warning("Order summary: unusable next_date %r -- storing none.", value)
        return None


def _templated(status: str, route: str, what_happened: str) -> dict:
    return {
        "status": status,
        "route": route,
        "what_happened": what_happened,
        "petitioner_directions": [],
        "respondent_directions": [],
        "next_date": None,
        "next_date_purpose": "",
        "is_routine_adjournment": False,
        "error": "",
        "llm_calls": 0,
    }


def _failed(route: str, error: str, *, llm_calls: int) -> dict:
    return {
        "status": CourtOrder.SUMMARY_FAILED,
        "route": route,
        "what_happened": "",
        "petitioner_directions": [],
        "respondent_directions": [],
        "next_date": None,
        "next_date_purpose": "",
        "is_routine_adjournment": False,
        "error": error,
        "llm_calls": llm_calls,
    }


def _order_text(order: CourtOrder) -> str:
    """The order's extracted text, post-OCR.

    Reads Document.extracted_text rather than re-extracting: the worker
    has already done extraction (and OCR for scanned PDFs) by the time
    this runs, and repeating it would double the slowest part of ingest.
    An order with no document at all reads as empty, which routes to
    UNREADABLE -- the correct answer.
    """
    document = getattr(order, "document", None)
    if document is None:
        return ""
    return document.extracted_text or ""


def _persist(order: CourtOrder, result: dict) -> CourtOrder:
    order.summary_status = result["status"]
    order.summary_route = result["route"]
    order.summary_what_happened = result["what_happened"]
    order.summary_petitioner_directions = result["petitioner_directions"]
    order.summary_respondent_directions = result["respondent_directions"]
    order.summary_next_date = result["next_date"]
    order.summary_next_date_purpose = result["next_date_purpose"]
    order.summary_is_routine_adjournment = result["is_routine_adjournment"]
    order.summary_error = result["error"]
    order.summary_llm_calls = result["llm_calls"]
    order.summary_generated_at = timezone.now()
    order.save(
        update_fields=[
            "summary_status",
            "summary_route",
            "summary_what_happened",
            "summary_petitioner_directions",
            "summary_respondent_directions",
            "summary_next_date",
            "summary_next_date_purpose",
            "summary_is_routine_adjournment",
            "summary_error",
            "summary_llm_calls",
            "summary_generated_at",
        ]
    )
    return order
