"""Where a district case is heard, in the terms the cause-list portal needs.

A district cause list is requested per COURT (one judge):

    state_code / dist_code / court_complex_code / est_code / "<est>^<court_no>"

What the system already has, and where from:

- The CNR case page (fetched on every refresh) carries the state, district
  and establishment codes in its "view QR code" link and the court number in
  `Court Number and Judge` ("1-CHIEF JUDGE"). It does NOT carry the
  court-complex code. (`ecourts_parsing.extract_locator_hints`)
- Cases set up through the cascade form have the full hierarchy in
  `tracking_config`; their court number comes from the latest stored fetch
  snapshot (`CourtFetchLog.fields_changed["snapshot"]["court_and_judge"]`).
- The complex is found by asking the district's complex list which complex
  holds the establishment (`1290019@2,6,11,20@N` holds est 2). That list is
  CAPTCHA-free and cached by the provider.

So the locator is filled, in order of cost: from stored data (free), from
the next refresh (free, already happening), and only then by one
captcha-free dropdown call (`complete_complex`).
"""

from __future__ import annotations

import logging
import re

from core.models import Case, CourtFetchLog

logger = logging.getLogger(__name__)

_COURT_NO = re.compile(r"^\s*(\d{1,4})\s*[-–.)]")


def court_no_from_text(text: str | None) -> str:
    """'1-CHIEF JUDGE' -> '1'; '' when the text carries no leading number
    (High Court 'Coram' strings do not)."""
    match = _COURT_NO.match(text or "")
    return match.group(1) if match else ""


def locator_from_hints(hints: dict | None, tracking_config: dict | None, existing: dict | None) -> dict | None:
    """A district locator from a fetch's hints, keeping any complex already
    resolved for the same establishment. None when the hints are partial."""
    hints = hints or {}
    state, dist, est, court_no = (str(hints.get(k) or "") for k in ("state_code", "dist_code", "est_code", "court_no"))
    if not (state and dist and est and court_no):
        return None
    complex_code = ""
    config = tracking_config or {}
    if (
        str(config.get("state_code") or "") == state
        and str(config.get("dist_code") or "") == dist
        and str(config.get("est_code") or est) == est
    ):
        complex_code = str(config.get("court_complex_code") or "")
    if not complex_code and existing and existing.get("kind") == "district":
        if all(str(existing.get(k) or "") == v for k, v in (("state_code", state), ("dist_code", dist), ("est_code", est))):
            complex_code = str(existing.get("complex_code") or "")
    return {
        "kind": "district",
        "state_code": state,
        "dist_code": dist,
        "est_code": est,
        "complex_code": complex_code,
        "court_no": court_no,
    }


def derive_from_stored(case: Case) -> dict | None:
    """Everything derivable WITHOUT a portal call, or None.

    Only cascade-form district cases qualify (CNR-first cases store just the
    CNR); they still need their court number from a stored fetch snapshot."""
    config = case.tracking_config or {}
    if (case.court_type or config.get("court_type")) != "district":
        return None
    needed = ("state_code", "dist_code", "court_complex_code")
    if not all(config.get(k) for k in needed):
        return None
    est = str(config.get("est_code") or "")
    if not est:
        return None
    log = (
        CourtFetchLog.objects.filter(case=case, success=True)
        .exclude(fields_changed__isnull=True)
        .order_by("-timestamp")
        .first()
    )
    snapshot = ((log.fields_changed or {}).get("snapshot") or {}) if log else {}
    court_no = court_no_from_text(snapshot.get("court_and_judge"))
    if not court_no:
        return None
    return {
        "kind": "district",
        "state_code": str(config["state_code"]),
        "dist_code": str(config["dist_code"]),
        "est_code": est,
        "complex_code": str(config["court_complex_code"]),
        "court_no": court_no,
    }


def complete_complex(locator: dict, provider=None) -> dict | None:
    """Fill `complex_code` by finding which complex of the district lists
    this establishment. One captcha-free (and cached) dropdown call.

    Returns the completed locator, or None if no complex lists the est (the
    establishment code was wrong, or the portal changed) -- never a guess.
    """
    if locator.get("complex_code"):
        return locator
    from core.services.court_data.ecourts_provider import EcourtsProvider
    from bharat_courts.districtcourts.parser import parse_complex_value

    provider = provider or EcourtsProvider()
    complexes = provider.list_complexes(locator["state_code"], locator["dist_code"])
    matches = []
    for value in complexes:
        code, ests, _needs_est = parse_complex_value(value)
        if locator["est_code"] in ests:
            matches.append(code)
    if len(matches) != 1:
        logger.warning(
            "Locator %s: %d complexes list establishment %s -- not guessing.",
            locator, len(matches), locator["est_code"],
        )
        return None
    return {**locator, "complex_code": matches[0]}
