"""Approval of one draft revision.

The only writer of AssistantDraftRevision.approved_at / approved_by /
approved_hash. Approval happens only on the advocate's explicit request to
the approve endpoint: nothing here is called by generation, the worker or a
model.
"""

from __future__ import annotations

import hashlib
import json

from django.db import transaction
from django.utils import timezone

from core.models import (
    AssistantDraft,
    AssistantDraftRevision,
    Case,
    CaseEvent,
    Document,
    Hearing,
    Task,
)
from core.services.drafting.schema import DraftValidationError, validate_body


class DraftNotFound(Exception):
    """The draft or revision does not exist for this owner. Answer 404."""


class DraftConflict(Exception):
    """A refusal the UI can act on: `code` is a DraftErrorCode, `extra` the
    additional response fields."""

    def __init__(self, code: str, detail: str, *, status: int = 409, **extra):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status
        self.extra = extra


def body_hash(body) -> str:
    """sha256 of the canonical JSON of a draft body."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_EVIDENCE_MODELS = {
    "hearing": Hearing,
    "task": Task,
    "event": CaseEvent,
    "document": Document,
}


def _evidence_present(entry, *, owner, case_id) -> bool:
    ref = entry.get("ref") if isinstance(entry, dict) else None
    if not isinstance(ref, dict):
        return False
    kind, record_id = ref.get("kind"), ref.get("id")
    if not isinstance(record_id, int) or isinstance(record_id, bool):
        return False
    if kind == "case":
        return record_id == case_id and Case.objects.filter(owner=owner, pk=case_id).exists()
    model = _EVIDENCE_MODELS.get(kind)
    if model is None:
        return False
    return model.objects.filter(owner=owner, case_id=case_id, pk=record_id).exists()


def missing_evidence(revision: AssistantDraftRevision, *, owner, case_id) -> list[str]:
    """Labels of the evidence entries whose record is no longer the owner's
    record on this case."""
    missing: list[str] = []
    for entry in revision.evidence or []:
        if not _evidence_present(entry, owner=owner, case_id=case_id):
            label = entry.get("label") if isinstance(entry, dict) else ""
            missing.append(str(label or "A source that is no longer available"))
    return missing


def approve_revision(*, draft_id, revision_id, user, acknowledge_open_items=False) -> AssistantDraft:
    """Approve `revision_id` of the owner's draft, or raise.

    Idempotent: approving an already approved revision changes nothing.
    """
    with transaction.atomic():
        draft = (
            AssistantDraft.objects.select_for_update()
            .filter(owner=user, pk=draft_id)
            .first()
        )
        if draft is None:
            raise DraftNotFound()
        revision = AssistantDraftRevision.objects.filter(
            owner=user, draft=draft, pk=revision_id
        ).first()
        if revision is None:
            raise DraftNotFound()

        if draft.current_revision_id != revision.id or draft.status != AssistantDraft.STATUS_READY:
            raise DraftConflict(
                "stale_revision",
                "This draft has changed. Reload it before approving.",
                current_revision_id=draft.current_revision_id,
            )
        if revision.approved_at is not None:
            return draft

        body = revision.body
        allowed = [
            entry.get("id") for entry in revision.evidence or [] if isinstance(entry, dict)
        ]
        try:
            validate_body(body, allowed_evidence=[e for e in allowed if isinstance(e, str)])
        except DraftValidationError as exc:
            raise DraftConflict(
                "invalid_body",
                "This version cannot be approved as it is. Edit it and try again.",
                status=400,
                errors=exc.errors,
            )

        missing = missing_evidence(revision, owner=user, case_id=draft.case_id)
        if missing:
            raise DraftConflict(
                "evidence_changed",
                "Some records this draft relies on are no longer on this case.",
                items=missing,
            )

        open_items = list(body.get("verification_items") or []) + list(revision.missing_facts or [])
        if open_items and acknowledge_open_items is not True:
            raise DraftConflict(
                "needs_acknowledgement",
                "Confirm the open items before approving.",
                items=open_items,
            )

        # The model's save() refuses updates on purpose; this is the one
        # sanctioned write to an existing revision.
        AssistantDraftRevision.objects.filter(
            pk=revision.pk, approved_at__isnull=True
        ).update(
            approved_at=timezone.now(),
            approved_by=user,
            approved_hash=body_hash(body),
        )
        return draft
