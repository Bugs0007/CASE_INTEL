"""The High Court jurisdiction table (frontend-next/lib/hc-jurisdiction.ts) against
the court library's registry.

The table lives with the map in the frontend, one line per court. This reads that
file (no Node needed) and checks it from the backend side: every High Court the
registry knows is in it, nothing else is, and no state or territory is given to two
courts. The other half, that every location the map draws belongs to exactly one
court, is frontend-next/__tests__/hc-jurisdiction.test.tsx.
"""

import re
from pathlib import Path

from core.services.high_court_registry import high_courts

TABLE = Path(__file__).resolve().parents[2] / "frontend-next" / "lib" / "hc-jurisdiction.ts"
LINE = re.compile(r'^  ([a-z]+): \[([^\]]*)\],\s*$')


def _table() -> dict[str, list[str]]:
    block = TABLE.read_text(encoding="utf-8").split("export const JURISDICTION", 1)[1].split("};", 1)[0]
    out: dict[str, list[str]] = {}
    for line in block.splitlines():
        match = LINE.match(line)
        if match:
            out[match.group(1)] = re.findall(r'"([a-z]+)"', match.group(2))
    return out


def test_every_registry_high_court_is_in_the_table_and_nothing_else():
    table = _table()
    registry = {court["code"] for court in high_courts()}
    assert len(registry) == 25
    assert set(table) == registry


def test_no_state_or_territory_belongs_to_two_courts():
    seen: dict[str, str] = {}
    for court, ids in _table().items():
        for location in ids:
            assert location not in seen, f"{location} is given to both {seen[location]} and {court}"
            seen[location] = court
    assert len(seen) == 36  # every location @svg-maps/india draws


def test_every_court_serves_at_least_one_location():
    assert all(ids for ids in _table().values())


def test_the_arrangements_the_courts_themselves_have():
    table = _table()
    assert sorted(table["bombay"]) == ["dd", "dn", "ga", "mh"]
    assert sorted(table["punjab"]) == ["ch", "hr", "pb"]
    assert sorted(table["gauhati"]) == ["ar", "as", "mz", "nl"]
    assert table["kerala"] == ["kl", "ld"] and table["madras"] == ["tn", "py"] and table["calcutta"] == ["wb", "an"]
