"""Record a limitation deadline on a case as a Task."""

from __future__ import annotations

from datetime import date

from core.models import Task
from core.services.tasks import upsert_system_task

from .compute import LimitationComputation, compute_deadline
from .rules import get_rule


class InvalidSourceOrderError(ValueError):
    """The order given as the deadline's source isn't on this case."""


def add_limitation_deadline(
    case, *, rule_key: str, trigger_date: date, source_order=None
) -> tuple[Task, str, LimitationComputation]:
    """Compute the deadline and create (or refresh) its Task.

    Returns (task, outcome, computation). The advocate chose the rule and the
    date, so the task is not marked for review. Adding the same rule and
    date again is idempotent; a deadline the advocate has since edited is
    left as they left it.
    """
    rule = get_rule(rule_key)
    if source_order is not None and source_order.case_id != case.id:
        raise InvalidSourceOrderError("That order is not on this case.")

    computation = compute_deadline(rule, trigger_date)
    task, outcome = upsert_system_task(
        owner=case.owner,
        case=case,
        kind=Task.KIND_LIMITATION,
        dedup_key=f"limitation:{case.id}:{rule.key}:{trigger_date.isoformat()}",
        title=f"Last day: {rule.label}",
        description="\n".join(computation.notes),
        due_date=computation.last_day,
        due_date_basis=Task.BASIS_LIMITATION_RULE,
        source_order=source_order,
        source_text=rule.citation,
        rule_key=rule.key,
        trigger_date=trigger_date,
    )
    return task, outcome, computation
