"""Entries <-> hearings.

Matching order, strongest first:
  1. CNR -- exact, and the only key district lists need (every row prints
     one; Orissa's High Court list does too).
  2. (TYPE, NUMBER, YEAR) via normalize.canonical_case_key, from every field
     a Case might carry its number in.

All hits are returned, in list order. The first is the primary one (the
earliest-printed hit in fetch order is the one the advocate is called on);
the rest are kept so a matter listed in both a main and a supplementary
list shows both.

Never matched on, by design: connected/IA lines (an IA number is not the
case's identity) and filing-number entries (a filing number and a
registration number are separate series that collide freely).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.models import Case

from .base import CauseListEntry
from .normalize import CaseKey, canonical_case_key, normalize_cnr


@dataclass(frozen=True)
class CaseIdentity:
    cnr: str
    keys: frozenset[CaseKey]

    @property
    def empty(self) -> bool:
        return not self.cnr and not self.keys


@dataclass(frozen=True)
class Match:
    entry: CauseListEntry
    matched_by: str  # "cnr" | "case_key"


@dataclass
class EntryIndex:
    by_cnr: dict[str, list[CauseListEntry]] = field(default_factory=dict)
    by_key: dict[CaseKey, list[CauseListEntry]] = field(default_factory=dict)
    total: int = 0
    seq: dict[int, int] = field(default_factory=dict)  # id(entry) -> arrival order

    def add(self, entries: list[CauseListEntry], court: str | None = None) -> None:
        for entry in entries:
            self.seq[id(entry)] = self.total
            self.total += 1
            cnr = normalize_cnr(entry.cnr)
            if cnr:
                self.by_cnr.setdefault(cnr, []).append(entry)
            if entry.is_filing_number or not entry.case_token:
                continue
            key = canonical_case_key(entry.case_token, court)
            if key is not None:
                self.by_key.setdefault(key, []).append(entry)


def identity_for_case(case: Case, court: str | None = None) -> CaseIdentity:
    """Every identity a case might be listed under.

    Drawn from several fields because no single one is reliable:
    `case_number` is free text that the advocate-import fills from the
    portal's number when it has one and falls back to the CNR when it
    doesn't, and `tracking_config` carries case_type/case_number/year only
    for cascade-form setups (CNR-first setups have just court_type + cnr).
    A case yielding no identity at all is "unmatchable", reported as such --
    never as "not listed".
    """
    keys: set[CaseKey] = set()
    for value in (case.case_number, case.case_number_raw, case.title):
        key = canonical_case_key(value or "", court)
        if key is not None:
            keys.add(key)

    config = case.tracking_config or {}
    case_type = str(config.get("case_type") or "").strip()
    number = str(config.get("case_number") or "").strip()
    year = str(config.get("year") or "").strip()
    if case_type and number and year:
        # District configs carry a portal code like "2^2" as case_type;
        # canonical_case_key rejects those (a code can't be matched against
        # a printed list), which is correct.
        key = canonical_case_key(f"{case_type}/{number}/{year}", court)
        if key is not None:
            keys.add(key)

    cnr = normalize_cnr(case.cnr_number) or normalize_cnr(config.get("cnr"))
    return CaseIdentity(cnr=cnr, keys=frozenset(keys))


def find_matches(identity: CaseIdentity, index: EntryIndex) -> list[Match]:
    """All entries for this identity, CNR hits first, no duplicates."""
    seen: set[int] = set()
    matches: list[Match] = []

    def take(entries: list[CauseListEntry], how: str) -> None:
        for entry in entries:
            if id(entry) in seen:
                continue
            seen.add(id(entry))
            matches.append(Match(entry=entry, matched_by=how))

    if identity.cnr:
        take(index.by_cnr.get(identity.cnr, []), "cnr")
    for key in sorted(identity.keys):
        take(index.by_key.get(key, []), "case_key")
    # Primary = the earliest hit in fetch/list order, whatever found it.
    matches.sort(key=lambda m: index.seq.get(id(m.entry), 0))
    return matches
