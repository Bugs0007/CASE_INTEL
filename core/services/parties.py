"""Who the parties are, and which one is the advocate's client -- one
answer for every screen and document.

Petitioner/respondent come from the court record when there is one
(Case.petitioner_name/respondent_name, kept current on every eCourts
fetch), else from an "X vs Y" title (conflict_check.split_title). Which is
"ours" comes from Case.user_party_role; with the role unknown there is no
"opposing party", only the two sides as the record names them.

Before this, the case overview showed "Plaintiff/Client: No client on
file" for a case whose title named both sides, and "Opposing party: N/A"
while the document generator already printed "The State of Telangana".

Also the court's name for documents: the tracking snapshot, a hearing's
location, and finally the CNR itself -- every High Court CNR's first four
letters name the court (HBHC = Telangana), so a case tracked by CNR never
has to be asked "which court?".
"""

from __future__ import annotations

from dataclasses import dataclass

# Formal names as they head a pleading. bharat_courts calls these
# "Telangana High Court" etc.; anything not listed reads "High Court of X".
_FORMAL_HC_NAMES = {
    "telangana": "High Court for the State of Telangana at Hyderabad",
    "andhra": "High Court of Andhra Pradesh at Amaravati",
}


@dataclass(frozen=True)
class Parties:
    petitioner: str
    respondent: str
    source: str  # "record", "title", or "" when neither names them
    role: str  # Case.user_party_role
    ours: str
    opposing: str

    def as_dict(self) -> dict:
        return {
            "petitioner": self.petitioner,
            "respondent": self.respondent,
            "source": self.source,
            "ours": self.ours,
            "opposing": self.opposing,
        }


def case_parties(case) -> Parties:
    petitioner = (case.petitioner_name or "").strip()
    respondent = (case.respondent_name or "").strip()
    source = "record" if (petitioner or respondent) else ""
    if not source:
        from core.services.conflict_check import split_title

        petitioner, respondent = split_title(case.title or "")
        source = "title" if (petitioner or respondent) else ""

    role = case.user_party_role or "unknown"
    ours = {"petitioner": petitioner, "respondent": respondent}.get(role, "")
    opposing = {"petitioner": respondent, "respondent": petitioner}.get(role, "")
    return Parties(petitioner, respondent, source, role, ours, opposing)


def court_name_from_cnr(cnr: str | None) -> str:
    """A High Court's formal name from its CNR prefix, or "" (district and
    unknown prefixes can't be named from the CNR alone)."""
    if not cnr:
        return ""
    try:
        from bharat_courts import infer_court_from_cnr

        court = infer_court_from_cnr(cnr)
    except Exception:  # noqa: BLE001 -- a lookup table miss is just "unknown"
        return ""
    if court is None or getattr(court.court_type, "value", court.court_type) != "high_court":
        return ""
    code = getattr(court, "code", "")
    if code in _FORMAL_HC_NAMES:
        return _FORMAL_HC_NAMES[code]
    state = court.name.replace("High Court", "").strip()
    return f"High Court of {state}" if state else court.name


def case_court_name(case) -> str:
    """The court for a document heading: the latest tracking snapshot, a
    hearing's recorded location, then the CNR prefix."""
    from core.models import Hearing
    from core.services.court_tracking import latest_snapshot

    snapshot = latest_snapshot(case) or {}
    if (snapshot.get("court_name") or "").strip():
        return snapshot["court_name"].strip()
    hearing = (
        Hearing.objects.filter(case=case)
        .exclude(location__isnull=True)
        .exclude(location="")
        .order_by("-hearing_date")
        .first()
    )
    if hearing is not None:
        return hearing.location
    return court_name_from_cnr(case.cnr_number)


def court_names_for_cases(cases) -> dict[int, str]:
    """{case_id: court name} for many cases in two queries -- the case list's
    twin of case_court_name (same order of preference: the latest tracking
    snapshot, a hearing's recorded location, the High Court the CNR names), for
    where a query per case would be an N+1. "" when no court is known.

    Like case_court_name, only the latest successful fetch is read: if that
    fetch carried no snapshot, the answer falls through to the hearing."""
    from django.db.models.fields.json import KeyTextTransform, KeyTransform

    from core.models import CourtFetchLog, Hearing

    cases = list(cases)
    ids = [case.id for case in cases]
    if not ids:
        return {}
    snapshot_courts = dict(
        CourtFetchLog.objects.filter(case_id__in=ids, success=True)
        .order_by("case_id", "-timestamp", "-id")
        .distinct("case_id")
        .annotate(court=KeyTextTransform("court_name", KeyTransform("snapshot", "fields_changed")))
        .values_list("case_id", "court")
    )
    hearing_locations = dict(
        Hearing.objects.filter(case_id__in=ids)
        .exclude(location__isnull=True)
        .exclude(location="")
        .order_by("case_id", "-hearing_date", "-id")
        .distinct("case_id")
        .values_list("case_id", "location")
    )
    return {
        case.id: (snapshot_courts.get(case.id) or "").strip()
        or hearing_locations.get(case.id, "")
        or court_name_from_cnr(case.cnr_number)
        for case in cases
    }
