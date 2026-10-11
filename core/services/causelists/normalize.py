"""Canonical case identities, used on BOTH sides of a match.

The same case is written differently by the list ("WP(C)/150/2026",
"WP 200448/2025", "1) Crl.Petn./103/2026 BRYAN ...", "ARB.P.-1379//2026")
and by the portal record a Case was created from. The key
(TYPE, NUMBER, YEAR) is built by stripping dots, spaces, brackets and
hyphens from the type, leading zeros from the number, then applying a
per-court alias table that lives in data/case_type_aliases.json -- data, not
if/else branches.

The alias tables ship EMPTY on purpose: an alias is only added when a real
list and a real portal record are seen to spell the same case type
differently after stripping, and nothing in the fixtures captured so far
does. The mechanism is exercised in tests with an injected table.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "case_type_aliases.json"

CaseKey = tuple[str, str, str]

# TYPE <sep> NUMBER <sep> YEAR. The type may carry dots, brackets, spaces and
# a trailing hyphen ("ARB.P.-1379//2026" collapses to ARB.P.-1379/2026).
_KEY_RE = re.compile(
    r"^\s*(?P<type>[A-Za-z][A-Za-z.()&\s\-]{0,28}?)\s*[/\-\s]\s*"
    r"(?P<num>\d{1,7})\s*(?:/|-|\s+of\s+|\s+)\s*(?P<year>\d{4})(?P<rest>\b.*)?$",
    re.IGNORECASE | re.DOTALL,
)
_FILING_SUFFIX_RE = re.compile(r"\s*/?\s*\(\s*filing\s*no\.?\s*\)\s*$", re.IGNORECASE)
_STRIP_TYPE_RE = re.compile(r"[.\s()\-_&]")
_CNR_RE = re.compile(r"^[A-Z]{4}[0-9]{12}$")


@lru_cache(maxsize=1)
def _alias_tables() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        court: {_strip(k): _strip(v) for k, v in table.items()}
        for court, table in raw.items()
        if isinstance(table, dict) and not court.startswith("_")
    }


def reset_alias_cache() -> None:
    """For tests that swap the alias file."""
    _alias_tables.cache_clear()


def _strip(value: str) -> str:
    return _STRIP_TYPE_RE.sub("", value or "").upper()


def canonical_case_key(raw: str | None, court: str | None = None) -> CaseKey | None:
    """'W.P.(C)/0150//2026' -> ('WPC', '150', '2026'); None if it isn't a
    case number. Never raises: None means "no identity to match on", which
    is a normal outcome for a CNR-numbered case.

    Trailing text after the year ("... BRYAN KHONGSDIR AND") is ignored, so
    a list that prints case number and party in one block still keys."""
    if not raw:
        return None
    text = _FILING_SUFFIX_RE.sub("", str(raw))
    text = re.sub(r"/{2,}", "/", text)
    match = _KEY_RE.match(text)
    if match is None:
        return None
    case_type = _strip(match.group("type"))
    if not case_type:
        return None
    number = match.group("num").lstrip("0") or "0"
    alias_table = _alias_tables()
    case_type = alias_table.get(court or "", {}).get(case_type) or alias_table.get(
        "_all", {}
    ).get(case_type) or case_type
    return case_type, number, match.group("year")


def is_filing_number(raw: str | None) -> bool:
    return bool(raw and _FILING_SUFFIX_RE.search(str(raw)))


def normalize_cnr(raw: str | None) -> str:
    """A 16-character eCourts CNR, upper-cased, or ''."""
    candidate = re.sub(r"[^A-Za-z0-9]", "", str(raw or "")).upper()
    return candidate if _CNR_RE.match(candidate) else ""
