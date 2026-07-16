"""
Provider-agnostic data contract for court case tracking.

Every CourtDataProvider.fetch_case() returns a CourtCaseData, regardless
of which underlying source (eCourts today, a paid API tomorrow) produced
it. Nothing outside core/services/court_data/ should construct these from
raw vendor SDK objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class HearingRecord:
    """One row of a case's hearing history."""

    hearing_date: date | None
    business_date: date | None = None
    purpose: str = ""
    judge: str = ""
    cause_list_type: str = ""


@dataclass
class CourtCaseData:
    """Normalized result of a single case lookup + history fetch."""

    cnr: str
    case_status: str = ""  # raw portal text, e.g. "CASE PENDING" / "CASE DISPOSED"
    case_stage: str = ""
    court_and_judge: str = ""
    court_name: str = ""
    petitioner: str = ""
    respondent: str = ""
    next_hearing_date: date | None = None
    first_hearing_date: date | None = None
    nature_of_disposal: str = ""
    hearing_history: list[HearingRecord] = field(default_factory=list)
