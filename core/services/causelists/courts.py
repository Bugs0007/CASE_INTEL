"""Which High Court (and bench) does a Case belong to?

Sources, strongest first:
  1. tracking_config.hc_court_code (the cascade setup) -- possibly a bench
     variant such as 'bombay-nagpur', which maps to a parent + bench code;
  2. the CNR's 4-letter prefix (CNR-first setups carry only court_type+cnr),
     via bharat_courts.infer_court_from_cnr, whose table was verified
     against the eCourts archive for all 25 HCs.
The bench comes from tracking_config.bench_code, then court_locator, then
a bench variant; otherwise it is unknown (None) -- an HC case page does not
say which bench it sits on.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import Case

from .hc_config import BENCH_VARIANTS


@dataclass(frozen=True)
class HCIdentity:
    hc_code: str
    bench_code: str | None
    source: str  # tracking_config | cnr


def _norm_code(code) -> str:
    return str(code or "").strip().lower()


def hc_identity(case: Case) -> HCIdentity | None:
    config = case.tracking_config or {}
    locator = case.court_locator or {}

    hc_code = _norm_code(config.get("hc_court_code")) or _norm_code(
        locator.get("hc_code") if locator.get("kind") == "hc" else ""
    )
    source = "tracking_config"
    variant_bench = None
    if hc_code in BENCH_VARIANTS:
        hc_code, variant_bench = BENCH_VARIANTS[hc_code]

    if not hc_code:
        hc_code = _hc_code_from_cnr(case.cnr_number or config.get("cnr"))
        source = "cnr"
    if not hc_code:
        return None

    bench = (
        str(config.get("bench_code") or "").strip()
        or (str(locator.get("bench_code") or "").strip() if locator.get("kind") == "hc" else "")
        or variant_bench
        or None
    )
    return HCIdentity(hc_code=hc_code, bench_code=bench, source=source)


def _hc_code_from_cnr(cnr) -> str:
    if not cnr:
        return ""
    from bharat_courts import infer_court_from_cnr

    court = infer_court_from_cnr(str(cnr))
    if court is None:
        return ""
    ctype = getattr(court.court_type, "value", court.court_type)
    return court.code if ctype == "high_court" else ""
