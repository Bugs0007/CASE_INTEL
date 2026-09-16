"""Limitation periods, as a reviewed lookup table.

Code, not database rows, on purpose: these are statutory periods, and a
change to one must go through code review with a citation -- never an
admin-panel edit. Same deliberately-small lookup-table style as
core/services/cause_list/registry.py.

Scope today: the Schedule to the Limitation Act, 1963 for the common
appeals, reviews, revisions and execution, plus the Supreme Court Rules,
2013 for special leave petitions. Special statutes (commercial courts,
consumer, arbitration, service, tax) prescribe their own periods and
aren't here -- a matter under one of them needs its statute's period, not
these.

EVERY ROW NEEDS LEGAL REVIEW before this ships: the periods below are
transcribed from the Schedule, but whether a row fits a given order is a
legal judgement the advocate makes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PERIOD_DAYS = "days"
PERIOD_YEARS = "years"

COURT_DISTRICT = "district"
COURT_HIGH_COURT = "high_court"
BOTH_COURTS = (COURT_DISTRICT, COURT_HIGH_COURT)

_KEY_RE = re.compile(r"^[a-z0-9_]+$")


@dataclass(frozen=True)
class LimitationRule:
    """One limitation period.

    key:                stable id, stored on Task.rule_key.
    label:              what is being filed, in plain words.
    citation:           the provision prescribing the period.
    period / period_unit: e.g. 90 days, 12 years.
    runs_from:          the event the period starts from, as the Schedule
                        words it -- shown to the advocate, who picks the
                        trigger date.
    court_types:        where the order being challenged would sit, for
                        filtering the picker (Case.court_type values).
    copy_time_excluded: Section 12(2) -- time to obtain a certified copy is
                        excluded (appeals, revisions, reviews).
    condonable:         Section 5 -- delay can be condoned on sufficient
                        cause. Not for Order XXI (execution) applications.
    note:               anything else the advocate must check.
    """

    key: str
    label: str
    citation: str
    period: int
    period_unit: str
    runs_from: str
    court_types: tuple[str, ...]
    copy_time_excluded: bool
    condonable: bool
    note: str = ""

    def __post_init__(self) -> None:
        if not _KEY_RE.match(self.key):
            raise ValueError(f"LimitationRule.key {self.key!r} must match {_KEY_RE.pattern}")
        if self.period <= 0:
            raise ValueError(f"LimitationRule {self.key!r} needs a positive period")
        if self.period_unit not in (PERIOD_DAYS, PERIOD_YEARS):
            raise ValueError(f"LimitationRule {self.key!r} has unknown unit {self.period_unit!r}")

    @property
    def period_text(self) -> str:
        return f"{self.period} {self.period_unit}"

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "citation": self.citation,
            "period": self.period,
            "period_unit": self.period_unit,
            "period_text": self.period_text,
            "runs_from": self.runs_from,
            "court_types": list(self.court_types),
            "copy_time_excluded": self.copy_time_excluded,
            "condonable": self.condonable,
            "note": self.note,
        }


LIMITATION_RULES: tuple[LimitationRule, ...] = (
    LimitationRule(
        key="appeal_to_high_court",
        label="Appeal to the High Court from a decree or order",
        citation="Limitation Act, 1963, Schedule, Article 116(a)",
        period=90,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the decree or order",
        court_types=(COURT_DISTRICT,),
        copy_time_excluded=True,
        condonable=True,
        note="Under the Code of Civil Procedure. Whether the appeal lies to the High Court or to "
        "a District Court depends on the pecuniary jurisdiction.",
    ),
    LimitationRule(
        key="appeal_to_other_court",
        label="Appeal to a court other than the High Court from a decree or order",
        citation="Limitation Act, 1963, Schedule, Article 116(b)",
        period=30,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the decree or order",
        court_types=(COURT_DISTRICT,),
        copy_time_excluded=True,
        condonable=True,
        note="Under the Code of Civil Procedure, e.g. to the District Court.",
    ),
    LimitationRule(
        key="appeal_within_high_court",
        label="Appeal from a decree or order of a High Court to the same High Court",
        citation="Limitation Act, 1963, Schedule, Article 117",
        period=30,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the decree or order",
        court_types=(COURT_HIGH_COURT,),
        copy_time_excluded=True,
        condonable=True,
        note="Intra-court appeals (e.g. Letters Patent). Check the High Court's own rules: writ "
        "appeals may be governed by them rather than this Article.",
    ),
    LimitationRule(
        key="criminal_appeal_to_high_court",
        label="Criminal appeal to the High Court from a sentence (other than death)",
        citation="Limitation Act, 1963, Schedule, Article 115(b)(i)",
        period=60,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the sentence or order",
        court_types=(COURT_DISTRICT,),
        copy_time_excluded=True,
        condonable=True,
        note="Appeals against a death sentence (Article 115(a), 30 days) and against acquittal "
        "(Article 114) have different periods and are not covered here.",
    ),
    LimitationRule(
        key="criminal_appeal_to_other_court",
        label="Criminal appeal to a court other than the High Court from a sentence",
        citation="Limitation Act, 1963, Schedule, Article 115(b)(ii)",
        period=30,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the sentence or order",
        court_types=(COURT_DISTRICT,),
        copy_time_excluded=True,
        condonable=True,
    ),
    LimitationRule(
        key="review",
        label="Review of a judgment by the same court (not the Supreme Court)",
        citation="Limitation Act, 1963, Schedule, Article 124",
        period=30,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the decree or order",
        court_types=BOTH_COURTS,
        copy_time_excluded=True,
        condonable=True,
    ),
    LimitationRule(
        key="revision",
        label="Revision under the Code of Civil Procedure or the criminal procedure code",
        citation="Limitation Act, 1963, Schedule, Article 131",
        period=90,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the decree, order or sentence sought to be revised",
        court_types=BOTH_COURTS,
        copy_time_excluded=True,
        condonable=True,
    ),
    LimitationRule(
        key="slp_supreme_court",
        label="Special leave petition to the Supreme Court against a High Court judgment",
        citation="Supreme Court Rules, 2013, Order XXII, Rule 2(1)",
        period=90,
        period_unit=PERIOD_DAYS,
        runs_from="the date of the judgment or order",
        court_types=(COURT_HIGH_COURT,),
        copy_time_excluded=True,
        condonable=True,
        note="Where the High Court refused a certificate of fitness, the period is 60 days from "
        "that refusal instead.",
    ),
    LimitationRule(
        key="execution_of_decree",
        label="Execution of a decree (other than a decree for a mandatory injunction)",
        citation="Limitation Act, 1963, Schedule, Article 136",
        period=12,
        period_unit=PERIOD_YEARS,
        runs_from="the date the decree becomes enforceable",
        court_types=BOTH_COURTS,
        copy_time_excluded=False,
        condonable=False,
    ),
)

_RULES_BY_KEY = {rule.key: rule for rule in LIMITATION_RULES}


class UnknownLimitationRuleError(ValueError):
    pass


def get_rule(key: str) -> LimitationRule:
    try:
        return _RULES_BY_KEY[key]
    except KeyError:
        raise UnknownLimitationRuleError(f"Unknown limitation rule {key!r}.") from None


def rules_for_court(court_type: str | None) -> list[LimitationRule]:
    """Rules relevant to a case in `court_type`; all of them if unknown."""
    if court_type not in BOTH_COURTS:
        return list(LIMITATION_RULES)
    return [rule for rule in LIMITATION_RULES if court_type in rule.court_types]
