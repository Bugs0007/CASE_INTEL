"""The High Courts the advocate search can offer, straight from bharat-courts'
registry, grouped one per High Court.

The registry has 29 entries for 25 High Courts: an entry per bench of a court that
has them (`bombay`, `bombay-nagpur`, ...). It carries bench NAMES only, never the
portal's bench codes: those come from the portal itself (`list_benches`, a
CAPTCHA-free call the app already caches), so a court's real benches are read
from there (see views/high_court_search.py).

`supported` answers one question: can the advocate search be pointed at this
court? Nothing is verified against the live portal per court yet (that needs a
CAPTCHA-gated search), so a court is supported unless the library is known to
have no route to it. Calcutta is the one such court: bharat-courts reaches it
through a separate client that can only search orders by case number.
"""

from __future__ import annotations

from bharat_courts import list_all_courts

# court code -> why it cannot be searched by advocate through the installed library
UNSUPPORTED: dict[str, str] = {
    "calcutta": (
        "Calcutta High Court runs its own portal; the installed court library can only search its "
        "orders by case number, not by advocate."
    ),
}


def high_courts() -> list[dict]:
    """One dict per High Court: {code, name, state_code, registry_benches,
    supported, support_note}. `code` is the bench-less registry entry's code, the
    one `EcourtsProvider.list_benches` and the search take."""
    by_state: dict[str, list] = {}
    for court in list_all_courts():
        if court.court_type.value == "high_court":
            by_state.setdefault(str(court.state_code), []).append(court)
    groups = []
    for state_code, entries in by_state.items():
        base = next((c for c in entries if not c.bench), entries[0])
        note = UNSUPPORTED.get(base.code, "")
        groups.append(
            {
                "code": base.code,
                "name": base.name,
                "state_code": state_code,
                "registry_benches": [{"code": c.code, "name": c.bench} for c in entries if c.bench],
                "supported": not note,
                "support_note": note,
            }
        )
    return sorted(groups, key=lambda g: g["name"])


def get_high_court(code: str) -> dict | None:
    return next((g for g in high_courts() if g["code"] == code), None)


def is_default_bench(bench_code: str, bench_name: str, registry_benches: list[dict]) -> bool:
    """Which of a court's portal benches start ticked: the principal seat (portal
    code 1) and every bench the registry names (Bombay: Aurangabad, Nagpur, Goa).
    The portal can list more (Bombay's Original Side, a Kolhapur bench, a TORTS
    court); those are offered, unticked."""
    if str(bench_code) == "1":
        return True
    lowered = (bench_name or "").lower()
    return any(b["name"] and b["name"].lower() in lowered for b in registry_benches)
