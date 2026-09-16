"""Conflict of interest check at intake.

Before a matter is taken on, its parties are compared with every party on
the advocate's existing cases. A conflict is a party appearing on OPPOSITE
sides: the new matter's opponent is (or resembles) an existing client, or
the new client is an opponent in an existing case. The same client in two
matters, or the same opponent twice, is not a conflict and isn't reported.

Where a case's party role is unknown, which side a court-record name sits
on is unknown too. Those comparisons are still reported, as "role unknown",
but only for close matches -- otherwise every repeat client on an imported
case would be flagged.

Scope is one advocate's own cases, always: comparing against another
tenant's cases would reveal their client list. (A firm-wide check isn't
possible while each advocate is their own tenant.)

This warns; it never blocks. Fuzzy name matches produce false positives,
two people can share a name, and an advocate may act with consent. The
interactive intake paths require an explicit acknowledgement, which is
recorded in the case's activity log.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from core.models import ActivityLog, Case

from .name_matching import could_match, name_similarity, party_tokens, split_parties

LIKELY_MIN_SCORE = 92
POSSIBLE_MIN_SCORE = 80

BAND_LIKELY = "likely"
BAND_POSSIBLE = "possible"

KIND_ADVERSE = "adverse"
KIND_ROLE_UNKNOWN = "role_unknown"

SIDE_OWN = "own"
SIDE_OTHER = "other"
SIDE_UNKNOWN = "unknown"

_TITLE_VS_RE = re.compile(r"\s+(?:vs\.?|v\.|v/s|versus)\s+", re.I)


@dataclass(frozen=True)
class Party:
    name: str
    side: str
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class ConflictHit:
    kind: str
    band: str
    score: int
    new_party: str
    new_side: str
    existing_party: str
    existing_side: str
    case_id: int
    case_number: str
    case_title: str

    def to_dict(self) -> dict:
        return asdict(self)


def parties_for(
    *,
    petitioner: str = "",
    respondent: str = "",
    client_name: str = "",
    opposing_party: str = "",
    user_party_role: str = "unknown",
    contact_names: tuple[str, ...] = (),
) -> list[Party]:
    """The parties of one matter, each placed on the advocate's side, the
    other side, or unknown.

    Court-record names (petitioner/respondent) take their side from the
    party role. client_name, opposing_party and client contacts are already
    relative to the advocate, whatever the role.
    """
    if user_party_role == "petitioner":
        petitioner_side, respondent_side = SIDE_OWN, SIDE_OTHER
    elif user_party_role == "respondent":
        petitioner_side, respondent_side = SIDE_OTHER, SIDE_OWN
    else:
        petitioner_side = respondent_side = SIDE_UNKNOWN

    raw: list[tuple[str, str]] = []
    raw += [(name, petitioner_side) for name in split_parties(petitioner)]
    raw += [(name, respondent_side) for name in split_parties(respondent)]
    raw += [(name, SIDE_OWN) for name in split_parties(client_name)]
    raw += [(name, SIDE_OTHER) for name in split_parties(opposing_party)]
    raw += [(name, SIDE_OWN) for name in contact_names if name]

    parties = []
    for name, side in raw:
        tokens = party_tokens(name)
        if tokens:
            parties.append(Party(name=name.strip(), side=side, tokens=tokens))
    return parties


def parties_for_case(case: Case) -> list[Party]:
    petitioner, respondent = case.petitioner_name, case.respondent_name
    if not (petitioner or respondent):
        petitioner, respondent = split_title(case.title)
    return parties_for(
        petitioner=petitioner,
        respondent=respondent,
        client_name=case.client_name or "",
        opposing_party=case.opposing_party or "",
        user_party_role=case.user_party_role,
        contact_names=tuple(contact.name for contact in case.client_contacts.all()),
    )


def split_title(title: str) -> tuple[str, str]:
    """ "Ramesh Kumar vs State of Telangana" -> (petitioner, respondent)."""
    parts = _TITLE_VS_RE.split(title or "", maxsplit=1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip(), parts[1].strip()


def _relationship(new_side: str, existing_side: str) -> str | None:
    if SIDE_UNKNOWN in (new_side, existing_side):
        return KIND_ROLE_UNKNOWN
    if new_side != existing_side:
        return KIND_ADVERSE
    return None  # same side: a repeat client or a repeat opponent


def _band(score: int) -> str | None:
    if score >= LIKELY_MIN_SCORE:
        return BAND_LIKELY
    if score >= POSSIBLE_MIN_SCORE:
        return BAND_POSSIBLE
    return None


def find_conflicts(
    owner,
    *,
    petitioner: str = "",
    respondent: str = "",
    client_name: str = "",
    opposing_party: str = "",
    user_party_role: str = "unknown",
    title: str = "",
    exclude_case_id: int | None = None,
) -> list[ConflictHit]:
    """Possible conflicts between a new matter and `owner`'s existing cases.

    `title` is only used for its "X vs Y" parties when no petitioner or
    respondent is given (manual entry). Returns at most one hit per existing
    case and new party -- the strongest -- adverse hits first.
    """
    if not (petitioner or respondent) and title:
        petitioner, respondent = split_title(title)
    new_parties = parties_for(
        petitioner=petitioner,
        respondent=respondent,
        client_name=client_name,
        opposing_party=opposing_party,
        user_party_role=user_party_role,
    )
    if not new_parties:
        return []

    cases = Case.objects.filter(owner=owner).prefetch_related("client_contacts")
    if exclude_case_id is not None:
        cases = cases.exclude(id=exclude_case_id)

    best: dict[tuple[int, str], ConflictHit] = {}
    for case in cases:
        for existing in parties_for_case(case):
            for new in new_parties:
                kind = _relationship(new.side, existing.side)
                if kind is None or not could_match(new.tokens, existing.tokens):
                    continue
                score = name_similarity(new.tokens, existing.tokens)
                band = _band(score)
                if band is None or (kind == KIND_ROLE_UNKNOWN and band != BAND_LIKELY):
                    continue
                key = (case.id, new.name)
                current = best.get(key)
                if current is None or _rank(kind, score) > _rank(current.kind, current.score):
                    best[key] = ConflictHit(
                        kind=kind,
                        band=band,
                        score=score,
                        new_party=new.name,
                        new_side=new.side,
                        existing_party=existing.name,
                        existing_side=existing.side,
                        case_id=case.id,
                        case_number=case.case_number,
                        case_title=case.title,
                    )
    return sorted(best.values(), key=lambda hit: _rank(hit.kind, hit.score), reverse=True)


def _rank(kind: str, score: int) -> tuple[int, int]:
    return (1 if kind == KIND_ADVERSE else 0, score)


# ---------------------------------------------------------------------------
# Intake helpers shared by the views and the import worker
# ---------------------------------------------------------------------------

CONFLICT_CODE = "conflict_check"


class ConflictCheckRequired(Exception):
    """Raised on an interactive intake path when possible conflicts exist
    and the advocate hasn't acknowledged them."""

    def __init__(self, hits: list[ConflictHit]):
        super().__init__(f"{len(hits)} possible conflict(s) need acknowledging.")
        self.hits = hits


def conflict_response_body(hits: list[ConflictHit]) -> dict:
    return {
        "code": CONFLICT_CODE,
        "detail": (
            "Parties in this matter resemble parties on the other side of cases "
            "you already have. Review them, then confirm to add the case anyway."
        ),
        "conflicts": [hit.to_dict() for hit in hits],
    }


def is_acknowledged(data) -> bool:
    value = data.get("acknowledge_conflicts") if hasattr(data, "get") else None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def describe_hits(hits: list[ConflictHit]) -> str:
    return "; ".join(
        f"{hit.new_party} ~ {hit.existing_party} ({hit.case_number}, {hit.kind.replace('_', ' ')}, "
        f"{hit.band})"
        for hit in hits
    )


def record_acknowledgement(case: Case, hits: list[ConflictHit]) -> None:
    ActivityLog.objects.create(
        owner=case.owner,
        case=case,
        activity_type="conflict_acknowledged",
        description=f"Added despite {len(hits)} possible conflict(s): {describe_hits(hits)}"[:5000],
    )


def record_flagged(case: Case, hits: list[ConflictHit]) -> None:
    ActivityLog.objects.create(
        owner=case.owner,
        case=case,
        activity_type="conflict_flagged",
        description=f"Possible conflict(s) found at import: {describe_hits(hits)}"[:5000],
    )
