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

    def to_dict(self) -> dict:
        """JSON-safe representation for storage in a JSONField (dates
        aren't natively JSON-serializable) -- see
        core/models/court_tracking_preview.py, which persists this as part
        of the preview -> confirm handoff."""
        return {
            "cnr": self.cnr,
            "case_status": self.case_status,
            "case_stage": self.case_stage,
            "court_and_judge": self.court_and_judge,
            "court_name": self.court_name,
            "petitioner": self.petitioner,
            "respondent": self.respondent,
            "next_hearing_date": self.next_hearing_date.isoformat() if self.next_hearing_date else None,
            "first_hearing_date": self.first_hearing_date.isoformat() if self.first_hearing_date else None,
            "nature_of_disposal": self.nature_of_disposal,
            "hearing_history": [
                {
                    "hearing_date": h.hearing_date.isoformat() if h.hearing_date else None,
                    "business_date": h.business_date.isoformat() if h.business_date else None,
                    "purpose": h.purpose,
                    "judge": h.judge,
                    "cause_list_type": h.cause_list_type,
                }
                for h in self.hearing_history
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "CourtCaseData":
        """Inverse of to_dict() -- reconstructs the dataclass (and its date
        fields) from the JSON-safe form stored in a CourtTrackingPreview row."""
        return cls(
            cnr=payload["cnr"],
            case_status=payload.get("case_status", ""),
            case_stage=payload.get("case_stage", ""),
            court_and_judge=payload.get("court_and_judge", ""),
            court_name=payload.get("court_name", ""),
            petitioner=payload.get("petitioner", ""),
            respondent=payload.get("respondent", ""),
            next_hearing_date=date.fromisoformat(payload["next_hearing_date"]) if payload.get("next_hearing_date") else None,
            first_hearing_date=date.fromisoformat(payload["first_hearing_date"]) if payload.get("first_hearing_date") else None,
            nature_of_disposal=payload.get("nature_of_disposal", ""),
            hearing_history=[
                HearingRecord(
                    hearing_date=date.fromisoformat(h["hearing_date"]) if h.get("hearing_date") else None,
                    business_date=date.fromisoformat(h["business_date"]) if h.get("business_date") else None,
                    purpose=h.get("purpose", ""),
                    judge=h.get("judge", ""),
                    cause_list_type=h.get("cause_list_type", ""),
                )
                for h in payload.get("hearing_history", [])
            ],
        )
