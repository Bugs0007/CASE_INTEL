"""Compute the last day of a limitation period -- conservatively.

The date returned is the EARLIEST the deadline can be, with every reason it
might be later stated as a note rather than guessed at:

  - Section 12(1): the day the period runs from is excluded, so 30 days
    from 1 January ends on 31 January. Applied.
  - Section 12(2): time taken to obtain a certified copy is excluded for
    appeals, revisions and reviews. NOT applied -- the copy dates aren't
    known here -- so noted.
  - Section 4: a period ending on a day the court is closed extends to the
    day it reopens. NOT applied -- without the court's holiday calendar,
    extending would risk a date that is too late -- so noted when the day
    is a Sunday.
  - Section 5: whether delay can be condoned, noted either way.

Getting a deadline too EARLY costs an advocate a day's margin; too LATE
costs the matter. Every simplification here errs early.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from .rules import PERIOD_DAYS, LimitationRule

VERIFY_NOTE = (
    "Computed from the limitation schedule as a guide. Verify the period, the start date and "
    "any special statute before relying on it."
)


@dataclass(frozen=True)
class LimitationComputation:
    rule: LimitationRule
    trigger_date: date
    last_day: date
    notes: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "rule": self.rule.to_dict(),
            "trigger_date": self.trigger_date,
            "last_day": self.last_day,
            "notes": list(self.notes),
        }


def compute_deadline(rule: LimitationRule, trigger_date: date) -> LimitationComputation:
    if rule.period_unit == PERIOD_DAYS:
        last_day = trigger_date + timedelta(days=rule.period)
    else:
        last_day = trigger_date + relativedelta(years=rule.period)

    notes = [
        f"{rule.period_text} from {trigger_date:%d %b %Y} ({rule.runs_from}), under {rule.citation}. "
        "The starting day itself is not counted (Section 12(1)).",
    ]
    if rule.copy_time_excluded:
        notes.append(
            "Time taken to obtain a certified copy of the order is also excluded (Section 12(2)) "
            "but is not counted here, so the real last day may be later."
        )
    if last_day.weekday() == 6:
        notes.append(
            "This falls on a Sunday. If the court is closed that day, filing on the day it "
            "reopens is in time (Section 4)."
        )
    if rule.condonable:
        notes.append(
            "Filing after this day needs an application to condone the delay, showing "
            "sufficient cause (Section 5)."
        )
    else:
        notes.append("Delay cannot be condoned under Section 5 for this application.")
    if rule.note:
        notes.append(rule.note)
    notes.append(VERIFY_NOTE)

    return LimitationComputation(rule=rule, trigger_date=trigger_date, last_day=last_day, notes=tuple(notes))
