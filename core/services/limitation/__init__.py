"""Limitation deadlines (roadmap item 1.2, phase a).

The advocate picks the rule and the date the period runs from; this
computes the last day and records it as a Task (kind "limitation") -- the
same list every other deadline lives in. Nothing here triggers on its own:
detecting a disposal and suggesting deadlines is a later phase.
"""

from .compute import LimitationComputation, compute_deadline
from .rules import (
    LIMITATION_RULES,
    LimitationRule,
    UnknownLimitationRuleError,
    get_rule,
    rules_for_court,
)
from .service import InvalidSourceOrderError, add_limitation_deadline

__all__ = [
    "LIMITATION_RULES",
    "InvalidSourceOrderError",
    "LimitationComputation",
    "LimitationRule",
    "UnknownLimitationRuleError",
    "add_limitation_deadline",
    "compute_deadline",
    "get_rule",
    "rules_for_court",
]
