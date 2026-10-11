"""Case -> adapter and listing target, or an honest "not covered".

`resolve_case` is pure (no network). Its contract is the fix for the
false-"not listed" bug: a case is only ever checked against a source that
actually covers *its* court, and a case no source covers resolves to
`unsupported`, never to a list it could not be in.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from core.models import Case

from .base import CauseListAdapter, Resolution
from .exceptions import CauseListNotConfiguredError

logger = logging.getLogger(__name__)

TELANGANA = "telangana_hc"
HCSERVICES = "hcservices_generic"
DISTRICT = "district_ecourts"
SUPREME = "supreme_court"

# Order a run visits adapters in: cheap and CAPTCHA-light first, the long
# district fan-out last so a time budget cuts the least valuable work.
ADAPTER_ORDER = [TELANGANA, HCSERVICES, DISTRICT, SUPREME]

_instances: dict[str, CauseListAdapter] = {}


def get_adapter(key: str) -> CauseListAdapter:
    if key in _instances:
        return _instances[key]
    if key == TELANGANA:
        from .adapters import telangana_hc

        adapter = telangana_hc.get_adapter()
    elif key == HCSERVICES:
        from .adapters import hcservices_generic

        adapter = hcservices_generic.get_adapter()
    elif key == DISTRICT:
        from .adapters import district_ecourts

        adapter = district_ecourts.get_adapter()
    elif key == SUPREME:
        from .adapters import supreme_court

        adapter = supreme_court.get_adapter()
    else:
        known = ", ".join(ADAPTER_ORDER)
        raise CauseListNotConfiguredError(f"Unknown cause-list adapter {key!r}. Known: {known}.")
    _instances[key] = adapter
    return adapter


def all_adapter_keys() -> list[str]:
    return list(ADAPTER_ORDER)


def configured_adapter_keys() -> list[str]:
    """The adapters the scheduled run covers (settings.CAUSE_LIST_ADAPTERS)."""
    keys = [k.strip() for k in getattr(settings, "CAUSE_LIST_ADAPTERS", []) if k.strip()]
    return keys or [TELANGANA, HCSERVICES, DISTRICT]


def resolve_case(case: Case) -> Resolution:
    """Which adapter/target covers this case? (No network.)"""
    from . import courts

    court_type = case.court_type or (case.tracking_config or {}).get("court_type")
    if court_type == "district":
        return get_adapter(DISTRICT).resolve(case)
    if court_type == "high_court":
        identity = courts.hc_identity(case)
        if identity is None:
            return Resolution.unsupported(
                "The High Court for this case could not be identified", HCSERVICES
            )
        if identity.hc_code == "telangana":
            return get_adapter(TELANGANA).resolve(case)
        return get_adapter(HCSERVICES).resolve(case)
    return Resolution.unsupported("The court for this case is not identified", "")


@dataclass(frozen=True)
class Coverage:
    status: str  # supported | unsupported | pending
    adapter: str
    label: str
    reason: str
    url: str


def coverage_for(case: Case) -> Coverage:
    """What the case page says about cause-list coverage (no network)."""
    res = resolve_case(case)
    if res.kind == "target":
        adapter = get_adapter(res.target.adapter)
        return Coverage("supported", adapter.key, res.target.label, "", adapter.coverage_url(case))
    label = ""
    url = ""
    if res.adapter:
        try:
            adapter = get_adapter(res.adapter)
            label = adapter.display_name
            url = adapter.coverage_url(case)
        except CauseListNotConfiguredError:
            pass
    return Coverage(res.kind, res.adapter, label, res.reason, url)
