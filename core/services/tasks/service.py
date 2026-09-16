"""Idempotent creation of system-generated tasks.

Generators (court-order directions, limitation rules) run more than once
for the same source -- a worker retry, a forced re-summary, a backfill
command, a party-role correction. Each generated task therefore carries a
`dedup_key` that is stable for its source, and this module turns "generate
again" into create-or-update on that key rather than a duplicate row.

Two things generation must never do:
  - overwrite a task the advocate has edited (`user_modified`) -- their
    date or wording wins, permanently;
  - reopen a task the advocate has completed or dismissed.
"""

from __future__ import annotations

import logging
from datetime import date

from django.db import IntegrityError, transaction

from core.models import Task

logger = logging.getLogger(__name__)

OUTCOME_CREATED = "created"
OUTCOME_UPDATED = "updated"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_SKIPPED = "skipped"  # edited, completed, or dismissed by the advocate

# Fields a regeneration is allowed to refresh on an untouched task.
_REFRESHABLE_FIELDS = (
    "case",
    "title",
    "description",
    "due_date",
    "due_date_basis",
    "source_order",
    "source_text",
    "rule_key",
    "trigger_date",
)


def upsert_system_task(
    *,
    owner,
    case,
    kind: str,
    dedup_key: str,
    title: str,
    due_date: date | None,
    due_date_basis: str,
    description: str = "",
    source_order=None,
    source_text: str = "",
    rule_key: str = "",
    trigger_date: date | None = None,
    needs_review: bool = False,
) -> tuple[Task, str]:
    """Create the task for `dedup_key`, or refresh it if still untouched.

    Returns (task, outcome), outcome being one of the OUTCOME_* constants.
    `needs_review` only applies on creation -- once the advocate has
    confirmed a suggestion, regenerating it must not flag it again.
    """
    if kind == Task.KIND_MANUAL:
        raise ValueError("upsert_system_task is for system-generated tasks, not manual ones.")
    if not dedup_key:
        raise ValueError("A system-generated task needs a dedup_key.")
    if case is not None and case.owner_id != owner.id:
        raise ValueError("A task's case must belong to the task's owner.")

    values = {
        "case": case,
        "title": title[:255],
        "description": description,
        "due_date": due_date,
        "due_date_basis": due_date_basis,
        "source_order": source_order,
        "source_text": source_text,
        "rule_key": rule_key,
        "trigger_date": trigger_date,
    }

    existing = Task.objects.filter(owner=owner, dedup_key=dedup_key).first()
    if existing is None:
        try:
            with transaction.atomic():
                task = Task.objects.create(
                    owner=owner,
                    kind=kind,
                    dedup_key=dedup_key,
                    needs_review=needs_review,
                    **values,
                )
            return task, OUTCOME_CREATED
        except IntegrityError:
            # A concurrent generator created the same task between the
            # lookup and the insert; fall through and treat it as existing.
            existing = Task.objects.get(owner=owner, dedup_key=dedup_key)

    if existing.user_modified or existing.status not in Task.OPEN_STATUSES:
        return existing, OUTCOME_SKIPPED

    changed = [
        field for field in _REFRESHABLE_FIELDS if getattr(existing, field) != values[field]
    ]
    if not changed:
        return existing, OUTCOME_UNCHANGED

    for field in changed:
        setattr(existing, field, values[field])
    existing.save(update_fields=[*changed, "updated_at"])
    logger.info("Refreshed system task %s (%s): %s", existing.id, dedup_key, ", ".join(changed))
    return existing, OUTCOME_UPDATED
