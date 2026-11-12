"""Worker entry point for a `draft_generation` job.

The job's payload is {"draft_id", "generation"}. One run produces the first
preview revision of that draft, or marks the draft failed with a fixed safe
sentence. Nothing is locked while the provider is called, and the preview is
committed only if the draft is still waiting for THIS generation: a late job
never overwrites a newer request.

Logs carry ids, counts, durations and exception class names only.
"""
from __future__ import annotations

import logging
import time

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.models import AssistantDraft, AssistantDraftRevision
from core.services.drafting.schema import SCHEMA_VERSION
from core.services.graph import draft_graph

logger = logging.getLogger(__name__)

ERROR_SOURCE_UNAVAILABLE = "A selected source is no longer available."
ERROR_GENERATION_FAILED = "The draft could not be generated. Try again."
ERROR_PROVIDER_UNAVAILABLE = "The drafting service is not available right now. Try again."

_MESSAGES = {
    draft_graph.ERROR_SOURCE_UNAVAILABLE: ERROR_SOURCE_UNAVAILABLE,
    draft_graph.ERROR_PROVIDER_UNAVAILABLE: ERROR_PROVIDER_UNAVAILABLE,
    draft_graph.ERROR_INVALID_OUTPUT: ERROR_GENERATION_FAILED,
    draft_graph.ERROR_CASE_UNAVAILABLE: ERROR_GENERATION_FAILED,
}

# What run_draft_generation returns when it does not raise.
COMMITTED = "committed"
SKIPPED = "skipped"  # nothing to do: no such draft, or a newer request owns it
DISCARDED = "discarded"  # generated, but the draft had moved on by commit time


class DraftGenerationError(Exception):
    """Generation failed. The message is one of the fixed safe sentences, so
    the worker can record it on the job as it does any other failure."""


def _pending(draft_id: int, owner_id: int, generation: int):
    return AssistantDraft.objects.filter(
        id=draft_id,
        owner_id=owner_id,
        generation=generation,
        status__in=AssistantDraft.PENDING_STATUSES,
    )


def _fail(job, draft_id: int, generation: int, message: str, error_class: str, started: float):
    """Mark the draft failed (only if this generation still owns it) and
    raise, so the worker records the job as failed."""
    _pending(draft_id, job.owner_id, generation).update(
        status=AssistantDraft.STATUS_FAILED, error=message, updated_at=timezone.now()
    )
    logger.warning(
        "Draft generation failed: job=%s draft=%s error_class=%s seconds=%.1f",
        job.id, draft_id, error_class, time.monotonic() - started,
    )
    raise DraftGenerationError(message) from None


def run_draft_generation(job) -> str:
    payload = job.payload if isinstance(job.payload, dict) else {}
    draft_id, generation = payload.get("draft_id"), payload.get("generation")
    draft = (
        AssistantDraft.objects.filter(id=draft_id, owner_id=job.owner_id).first()
        if isinstance(draft_id, int)
        else None
    )
    if (
        draft is None
        or draft.generation != generation
        or draft.status not in AssistantDraft.PENDING_STATUSES
    ):
        logger.info("Draft generation skipped: job=%s draft=%s", job.id, draft_id)
        return SKIPPED

    claimed = _pending(draft_id, job.owner_id, generation).update(
        status=AssistantDraft.STATUS_GENERATING, updated_at=timezone.now()
    )
    if not claimed:
        logger.info("Draft generation skipped: job=%s draft=%s", job.id, draft_id)
        return SKIPPED

    # No transaction and no row lock from here until the commit below.
    started = time.monotonic()
    try:
        state = draft_graph.run_draft_graph(
            owner_id=draft.owner_id,
            case_id=draft.case_id,
            subtype=draft.subtype,
            brief=draft.brief if isinstance(draft.brief, dict) else {},
        )
    except Exception as exc:  # noqa: BLE001 -- never let exception text reach draft.error
        _fail(job, draft_id, generation, ERROR_GENERATION_FAILED, type(exc).__name__, started)

    candidate = state.get("candidate")
    if state.get("error") or candidate is None:
        _fail(
            job,
            draft_id,
            generation,
            _MESSAGES.get(state.get("error"), ERROR_GENERATION_FAILED),
            state.get("error_class") or str(state.get("error")),
            started,
        )

    with transaction.atomic():
        locked = (
            AssistantDraft.objects.select_for_update()
            .filter(id=draft_id, owner_id=job.owner_id)
            .first()
        )
        if (
            locked is None
            or locked.generation != generation
            or locked.status not in AssistantDraft.PENDING_STATUSES
        ):
            logger.info(
                "Draft generation discarded (a newer request owns the draft): job=%s draft=%s",
                job.id, draft_id,
            )
            return DISCARDED
        last = locked.revisions.aggregate(last=Max("version"))["last"] or 0
        revision = AssistantDraftRevision.objects.create(
            owner_id=locked.owner_id,
            draft=locked,
            version=last + 1,
            source=AssistantDraftRevision.SOURCE_GENERATED,
            body=candidate["body"],
            schema_version=SCHEMA_VERSION,
            evidence=candidate["evidence"],
            missing_facts=candidate["missing_facts"],
            warnings=candidate["warnings"],
        )
        locked.current_revision = revision
        locked.status = AssistantDraft.STATUS_READY
        locked.error = ""
        locked.save(update_fields=["current_revision", "status", "error", "updated_at"])

    logger.info(
        "Draft generated: job=%s draft=%s version=%d evidence=%d llm_calls=%d seconds=%.1f",
        job.id, draft_id, revision.version, len(candidate["evidence"]),
        state.get("llm_calls") or 0, time.monotonic() - started,
    )
    return COMMITTED
