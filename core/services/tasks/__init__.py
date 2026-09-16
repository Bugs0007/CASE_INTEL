"""Tasks: the single surface for everything with a due date on a case.

`upsert_system_task` is the only way system code (order directions,
limitation rules) creates or updates a Task. See core/models/task.py.
"""

from .service import (
    OUTCOME_CREATED,
    OUTCOME_SKIPPED,
    OUTCOME_UNCHANGED,
    OUTCOME_UPDATED,
    upsert_system_task,
)

__all__ = [
    "OUTCOME_CREATED",
    "OUTCOME_SKIPPED",
    "OUTCOME_UNCHANGED",
    "OUTCOME_UPDATED",
    "upsert_system_task",
]
