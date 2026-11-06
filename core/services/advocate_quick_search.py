"""Quick search: remember which court complexes returned cases for an advocate.

A state-wide advocate search visits every court complex in a state. Most
advocates have cases in a handful, so after a search succeeds we keep the
complexes that returned at least one case and offer to search just those.

Stored on the owner's AdvocateSearchPreference.hierarchy_config, so it needs no
table of its own:

    {"state_code": "29", "dist_codes": ["1", "3"],
     "quick": {"29|suresh kumar": {"complexes": [{"dist_code", "dist_name",
         "complex_code", "est_code", "complex_name", "cases"}], "updated_at": iso}}}

Everything here is scoped to ONE owner: the history is read and written only
through that owner's own preference row.

What is remembered, and when: every search that finishes (not one that is
cancelled or fails outright) replaces the entries for exactly the court
complexes it searched successfully -- a complex that now returns nothing drops
out, one that returned cases is added or updated -- and leaves every other entry
alone. A complex the search could not read keeps whatever was remembered for
it. An import adds nothing of its own: the import job is handed case numbers
and court names, not the complex each came from, so the search that produced
those cases is what records them.
"""

from __future__ import annotations

import logging
import re

from django.utils import timezone

from core.models import AdvocateSearchPreference

logger = logging.getLogger(__name__)

# Different names/bar codes remembered per owner; the oldest are dropped past it.
MAX_REMEMBERED_QUERIES = 10


def query_key(advocate_name: str, bar_code: str, state_code: str) -> str:
    """One stable key per (state, advocate name or bar code): case and spacing
    never make two keys for the same person."""
    text = (bar_code or advocate_name or "").strip()
    text = re.sub(r"\s+", " ", text).lower()
    return f"{state_code}|{text}"


def _complex_id(entry: dict) -> tuple[str, str, str]:
    return (str(entry["dist_code"]), str(entry["complex_code"]), str(entry.get("est_code") or ""))


def remembered_complexes(owner, advocate_name: str, bar_code: str, state_code: str) -> list[dict]:
    """The complexes remembered for this advocate in this state (possibly [])."""
    preference = AdvocateSearchPreference.objects.filter(owner=owner).first()
    if preference is None:
        return []
    quick = (preference.hierarchy_config or {}).get("quick") or {}
    entry = quick.get(query_key(advocate_name, bar_code, state_code)) or {}
    return list(entry.get("complexes") or [])


def quick_search_summary(owner, advocate_name: str, bar_code: str, state_code: str) -> dict | None:
    """What the search page needs to offer a Quick search, or None when there
    is no history: {complexes, districts, updated_at}."""
    preference = AdvocateSearchPreference.objects.filter(owner=owner).first()
    if preference is None:
        return None
    quick = (preference.hierarchy_config or {}).get("quick") or {}
    entry = quick.get(query_key(advocate_name, bar_code, state_code))
    if not entry or not entry.get("complexes"):
        return None
    complexes = entry["complexes"]
    return {
        "complexes": len(complexes),
        "districts": len({c["dist_code"] for c in complexes}),
        "updated_at": entry.get("updated_at"),
    }


def remember_search(owner, *, advocate_name: str, bar_code: str, state_code: str, searched_ok: list[dict]) -> None:
    """Fold a finished search into the history.

    `searched_ok` has one dict per court complex the search read successfully,
    zero-case ones included: {dist_code, dist_name, complex_code, est_code,
    complex_name, cases}. Never raises -- a history write must not fail a
    search that found everything."""
    if not searched_ok or not (advocate_name or bar_code):
        return
    try:
        preference = AdvocateSearchPreference.objects.filter(owner=owner).first()
        if preference is None:
            preference = AdvocateSearchPreference(owner=owner, court_type="district", hierarchy_config={})
        config = dict(preference.hierarchy_config or {})
        quick = dict(config.get("quick") or {})
        key = query_key(advocate_name, bar_code, state_code)
        kept = {_complex_id(c): c for c in (quick.get(key) or {}).get("complexes", [])}

        for entry in searched_ok:
            identity = _complex_id(entry)
            kept.pop(identity, None)
            if entry.get("cases", 0) > 0:
                kept[identity] = {
                    "dist_code": str(entry["dist_code"]),
                    "dist_name": entry.get("dist_name", ""),
                    "complex_code": str(entry["complex_code"]),
                    "est_code": str(entry.get("est_code") or ""),
                    "complex_name": entry.get("complex_name", ""),
                    "cases": int(entry["cases"]),
                }

        quick.pop(key, None)  # re-insert last: dict order is "most recent last"
        if kept:
            quick[key] = {"complexes": list(kept.values()), "updated_at": timezone.now().isoformat()}
        while len(quick) > MAX_REMEMBERED_QUERIES:
            quick.pop(next(iter(quick)))

        config["quick"] = quick
        preference.hierarchy_config = config
        preference.save()
    except Exception:  # noqa: BLE001
        logger.exception("Could not remember advocate search hits for owner %s.", getattr(owner, "id", "?"))
