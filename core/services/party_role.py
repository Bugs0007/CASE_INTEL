"""Best-effort auto-detection of which side of a case is the advocate's own
client, by comparing the advocate name/bar code they searched with (see
core/views/advocate_search.py) against the raw per-party advocate names
eCourts recorded for the case (Case.party_advocate_data, captured by
core/services/court_tracking.py's _apply_case_data).

This is NOT expected to resolve every case -- eCourts frequently records
only one side's advocate (or none), and a bar-code search has nothing to
compare against at all (see below). Callers should treat "unknown" as a
normal, common outcome, not a failure -- the advocate sets the role
manually the rest of the time.
"""

from __future__ import annotations

import re

_HONORIFIC_RE = re.compile(r"\b(adv|advocate|sr|jr|shri|smt|mr|mrs|ms|dr)\b\.?", re.I)
_PUNCT_RE = re.compile(r"[.,]")
_WS_RE = re.compile(r"\s+")


def _normalize(name: str) -> str:
    name = name.lower()
    name = _HONORIFIC_RE.sub(" ", name)
    name = _PUNCT_RE.sub(" ", name)
    return _WS_RE.sub(" ", name).strip()


def _matches_any(search_name: str, candidates: list[str]) -> bool:
    normalized_search = _normalize(search_name)
    if not normalized_search:
        return False
    for candidate in candidates:
        normalized_candidate = _normalize(candidate)
        if not normalized_candidate:
            continue
        if normalized_search == normalized_candidate:
            return True
        if normalized_search in normalized_candidate or normalized_candidate in normalized_search:
            return True
    return False


def detect_party_role(advocate_name: str, bar_code: str, party_advocate_data: dict | None) -> str:
    """Returns "petitioner", "respondent", or "unknown".

    "unknown" whenever:
      - the search was by bar_code, not advocate_name -- party_advocate_data
        only ever holds free-text advocate NAMES scraped from eCourts
        case-history HTML (see ecourts_provider._extract_advocates); eCourts
        never exposes a bar code alongside them, so there is nothing to
        compare a bar code against.
      - party_advocate_data has no matching name on either side.
      - the searched name matches advocate names recorded for BOTH sides
        (ambiguous -- can't tell which one is actually the advocate's own
        client).
    """
    if not advocate_name:
        return "unknown"

    party_advocate_data = party_advocate_data or {}
    petitioner_match = _matches_any(
        advocate_name, party_advocate_data.get("petitioner_advocates") or []
    )
    respondent_match = _matches_any(
        advocate_name, party_advocate_data.get("respondent_advocates") or []
    )

    if petitioner_match and not respondent_match:
        return "petitioner"
    if respondent_match and not petitioner_match:
        return "respondent"
    return "unknown"
