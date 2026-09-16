"""The cached "state of the matter" paragraph for a case.

Same shape as the Order Overview: generated in the process_jobs worker,
read from a row (CaseBriefing) on every view. The difference is that a
case keeps moving, so the paragraph is stored with a fingerprint of the
facts it was written from. When new orders, hearings or court status change
those facts, the stored paragraph is stale; the advocate asks for a fresh
one from the prep sheet, which enqueues a `case_briefing` job.

Generation is on demand only -- never for every case on every change -- so
LLM calls are spent on cases someone is actually preparing.

The facts deliberately exclude the advocate's party role: the paragraph
names petitioner and respondent, and "your side" is applied at render time.
"""

from __future__ import annotations

import hashlib
import json
import logging

from django.utils import timezone

from core.models import CaseBriefing, CourtOrder, Hearing, ProcessingJob
from core.services.court_tracking import latest_snapshot

from .prompt import build_messages

logger = logging.getLogger(__name__)

MAX_BRIEFING_ORDERS = 5
MAX_BRIEFING_HEARINGS = 8
MAX_BRIEFING_CHARS = 2000

STATE_READY = "ready"  # paragraph matches the current facts
STATE_GENERATING = "generating"  # a job is queued or running
STATE_STALE = "stale"  # a paragraph exists but the facts have moved on
STATE_MISSING = "missing"  # never generated
STATE_FAILED = "failed"  # the last attempt for these facts failed
STATE_UNAVAILABLE = "unavailable"  # nothing to brief on yet


class BriefingError(Exception):
    """Raised by the worker entry point when generation fails."""


def briefing_inputs(case) -> dict:
    """The facts the paragraph is written from -- and fingerprinted on."""
    orders = list(
        CourtOrder.objects.filter(
            case=case,
            order_date__isnull=False,
            summary_status__in=[CourtOrder.SUMMARY_SUMMARIZED, CourtOrder.SUMMARY_NO_DIRECTIONS],
        ).order_by("-order_date", "-id")[:MAX_BRIEFING_ORDERS]
    )
    hearings = list(
        Hearing.objects.filter(case=case).order_by("-hearing_date")[:MAX_BRIEFING_HEARINGS]
    )
    snapshot = latest_snapshot(case) or {}

    return {
        "case_number": case.case_number,
        "court_type": case.court_type or "",
        "court_record": {
            "court": snapshot.get("court_name") or "",
            "case_status": snapshot.get("case_status") or "",
            "case_stage": snapshot.get("case_stage") or "",
        },
        "orders": [
            {
                "order_date": order.order_date.isoformat(),
                "what_happened": order.summary_what_happened,
                "petitioner_directions": order.summary_petitioner_directions or [],
                "respondent_directions": order.summary_respondent_directions or [],
                "next_date": order.summary_next_date.isoformat() if order.summary_next_date else None,
                "next_date_purpose": order.summary_next_date_purpose,
            }
            for order in reversed(orders)
        ],
        "hearings": [
            {
                "date": hearing.hearing_date.date().isoformat(),
                "purpose": hearing.purpose or "",
                "status": hearing.status,
            }
            for hearing in reversed(hearings)
        ],
    }


def fingerprint(inputs: dict) -> str:
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _has_material(inputs: dict) -> bool:
    record = inputs["court_record"]
    return bool(
        inputs["orders"] or inputs["hearings"] or record["case_status"] or record["case_stage"]
    )


def _active_job_exists(case) -> bool:
    return ProcessingJob.objects.filter(
        case=case, job_type="case_briefing", status__in=["queued", "running"]
    ).exists()


def get_briefing_state(case) -> dict:
    """What the prep sheet should show for the paragraph right now."""
    inputs = briefing_inputs(case)
    state = {"status": STATE_UNAVAILABLE, "text": "", "generated_at": None, "error": ""}
    if not _has_material(inputs):
        return state

    current = fingerprint(inputs)
    briefing = CaseBriefing.objects.filter(case=case).first()
    if briefing is not None:
        state.update(text=briefing.text, generated_at=briefing.generated_at)

    is_current = briefing is not None and briefing.input_fingerprint == current
    if is_current and briefing.status == CaseBriefing.STATUS_READY:
        state["status"] = STATE_READY
    elif _active_job_exists(case):
        state["status"] = STATE_GENERATING
    elif is_current and briefing.status == CaseBriefing.STATUS_FAILED:
        state.update(status=STATE_FAILED, error=briefing.error)
    elif briefing is not None and briefing.text:
        state["status"] = STATE_STALE
    else:
        state["status"] = STATE_MISSING
    return state


def request_briefing(case) -> tuple[dict, bool]:
    """Enqueue generation if the paragraph is missing, stale or failed.

    Returns (state, enqueued). Nothing is enqueued when the paragraph is
    already current, already being generated, or there is nothing to say.
    """
    state = get_briefing_state(case)
    if state["status"] in (STATE_READY, STATE_GENERATING, STATE_UNAVAILABLE):
        return state, False
    ProcessingJob.enqueue_case_briefing(case)
    state["status"] = STATE_GENERATING
    return state, True


def generate_case_briefing(case) -> CaseBriefing | None:
    """Worker entry point (job_type="case_briefing"). Idempotent.

    Raises BriefingError when the model call fails or returns nothing, after
    recording the failure on the row, so the job itself shows as failed.
    """
    inputs = briefing_inputs(case)
    if not _has_material(inputs):
        return None

    current = fingerprint(inputs)
    briefing = CaseBriefing.objects.filter(case=case).first()
    if (
        briefing is not None
        and briefing.status == CaseBriefing.STATUS_READY
        and briefing.input_fingerprint == current
    ):
        return briefing

    from core.services.ai_service_factory import get_llm_client

    try:
        raw = get_llm_client().generate(build_messages(inputs), temperature=0, max_tokens=600)
    except Exception as exc:  # noqa: BLE001 -- provider/network failures
        _record_failure(case, briefing, current, f"LLM call failed: {exc}")
        raise BriefingError(str(exc)) from exc

    text = _clean(raw)
    if not text:
        _record_failure(case, briefing, current, "The model returned an empty briefing.")
        raise BriefingError("The model returned an empty briefing.")

    briefing, _ = CaseBriefing.objects.update_or_create(
        case=case,
        defaults={
            "owner": case.owner,
            "status": CaseBriefing.STATUS_READY,
            "input_fingerprint": current,
            "text": text,
            "error": "",
            "llm_calls": 1,
            "generated_at": timezone.now(),
        },
    )
    logger.info("Case %s briefing generated (%d chars).", case.id, len(text))
    return briefing


def _record_failure(case, briefing, current: str, error: str) -> None:
    logger.warning("Case %s briefing failed: %s", case.id, error)
    # Keep any earlier paragraph: shown as out of date, it is more useful
    # than nothing while the failure is looked at.
    CaseBriefing.objects.update_or_create(
        case=case,
        defaults={
            "owner": case.owner,
            "status": CaseBriefing.STATUS_FAILED,
            "input_fingerprint": current,
            "text": briefing.text if briefing is not None else "",
            "error": error[:2000],
            "llm_calls": 1,
            "generated_at": timezone.now(),
        },
    )


def _clean(raw: str) -> str:
    """One paragraph of plain text, whatever wrapping the model added."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        first_line, _, rest = text.partition("\n")
        # A bare language tag ("text", "markdown") on the fence line.
        if rest.strip() and " " not in first_line.strip():
            text = rest
    text = text.strip().strip('"').strip()
    return " ".join(text.split())[:MAX_BRIEFING_CHARS]
