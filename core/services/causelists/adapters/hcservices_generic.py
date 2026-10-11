"""Every High Court on hcservices.ecourts.gov.in except Telangana (which has
its own adapter and the eight list types it was built against).

The FETCH is identical for all of them and driven by hc_config.py (state
code, bench codes, which benches are actually served). The PARSE is not:
each court prints its list in its own layout, so documents are read by the
parser family hc_config assigns (adapters/layouts/). A court is only
`supported` there once its parser passes golden tests on real fixtures.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

from .. import base, clock, courts, fetchlib, hc_config
from ..base import (
    PORTAL_HCSERVICES,
    CauseListAdapter,
    FetchResult,
    ListingTarget,
    ParsedDoc,
    RawDoc,
    Resolution,
)
from ..exceptions import CauseListFetchError, CauseListParseError
from . import _hcservices

logger = logging.getLogger(__name__)

KEY = "hcservices_generic"


class HCServicesGenericAdapter(CauseListAdapter):
    key = KEY
    display_name = "High Courts via eCourts HC Services"
    portal = PORTAL_HCSERVICES

    # ------------------------------------------------------------------
    def resolve(self, case) -> Resolution:
        ident = courts.hc_identity(case)
        if ident is None:
            return Resolution.unsupported("The High Court for this case could not be identified", KEY)
        cfg = hc_config.config_for(ident.hc_code)
        if cfg is None:
            return Resolution.unsupported(f"{ident.hc_code!r} is not a High Court cause lists are available for", KEY)
        if cfg.status != hc_config.SUPPORTED:
            return Resolution.unsupported(f"{cfg.name}: {cfg.reason}", KEY)

        incomplete = ""
        if ident.bench_code:
            bench = cfg.bench(ident.bench_code)
            if bench is None:
                return Resolution.unsupported(
                    f"{cfg.name}: bench code {ident.bench_code!r} is not one hcservices lists", KEY
                )
            if not bench.served:
                return Resolution.unsupported(
                    f"{cfg.name}, {bench.name}: its lists are on the portal's index but not served; "
                    "check the court's own site",
                    KEY,
                )
            benches = [bench]
        else:
            candidates = [b for b in cfg.benches if b.code not in cfg.skip_when_bench_unknown]
            benches = [b for b in candidates if b.served]
            if not benches:
                return Resolution.unsupported(f"{cfg.name}: {cfg.reason}", KEY)
            unserved = [b.name for b in candidates if not b.served]
            if unserved:
                # The case might sit on a bench whose lists we cannot read, so
                # absence from the benches we CAN read proves nothing.
                incomplete = (
                    f"bench not recorded for this case and {', '.join(unserved)} lists are not available"
                )

        codes = ",".join(b.code for b in benches)
        target = ListingTarget(
            adapter=KEY,
            key=f"{cfg.code}/{codes}",
            label=f"{cfg.name} ({', '.join(b.name for b in benches)})",
            params={
                "hc_code": cfg.code,
                "state_code": cfg.state_code,
                "benches": [{"code": b.code, "name": b.name} for b in benches],
                "parser": cfg.parser,
                "alias_court": cfg.code,
                "incomplete_scope": incomplete,
            },
        )
        return Resolution.for_target(target)

    def target_from_key(self, key: str) -> ListingTarget:
        """'andhra/1' or 'bombay/1,2' -> a target (for the doctor command)."""
        code, _, rest = key.partition("/")
        cfg = hc_config.config_for(code)
        if cfg is None:
            raise CauseListFetchError(f"unknown High Court {code!r}")
        wanted = [c for c in rest.split(",") if c] or [b.code for b in cfg.served_benches]
        benches = [b for b in cfg.benches if b.code in wanted]
        if not benches:
            raise CauseListFetchError(f"no bench of {code} matches {rest!r}")
        return ListingTarget(
            adapter=KEY,
            key=f"{cfg.code}/{','.join(b.code for b in benches)}",
            label=f"{cfg.name} ({', '.join(b.name for b in benches)})",
            params={
                "hc_code": cfg.code, "state_code": cfg.state_code,
                "benches": [{"code": b.code, "name": b.name} for b in benches],
                "parser": cfg.parser, "alias_court": cfg.code, "incomplete_scope": "",
            },
        )

    def coverage_url(self, case) -> str:
        return "https://hcservices.ecourts.gov.in/hcservices/main.php"

    # ------------------------------------------------------------------
    def fetch(self, target: ListingTarget, list_date: date, workdir: Path) -> FetchResult:
        budget = float(fetchlib.setting("CAUSE_LIST_HCSERVICES_BUDGET_SECONDS", 480))
        try:
            return fetchlib.run_bounded(self._fetch(target, list_date, workdir, budget), budget + 30)
        except CauseListFetchError as exc:
            return FetchResult(status="fetch_error", error=str(exc))
        except Exception as exc:  # noqa: BLE001 -- transport errors etc.
            logger.warning("hcservices fetch failed: %s: %s", type(exc).__name__, exc)
            return FetchResult(status="fetch_error", error=f"{type(exc).__name__}: {exc}"[:300])

    async def _fetch(self, target, list_date, workdir, budget) -> FetchResult:
        from bharat_courts import HCServicesClient

        pacer = fetchlib.Pacer()
        deadline = time.monotonic() + budget
        attempts = int(fetchlib.setting("CAUSE_LIST_CAPTCHA_ATTEMPTS_HC", 5))
        max_docs = int(fetchlib.setting("CAUSE_LIST_MAX_DOCS_PER_TARGET", 200))
        docs: list[RawDoc] = []
        total = 0
        none_available = 0
        captcha_failed = 0
        benches = target.params["benches"]
        async with HCServicesClient() as client:
            for bench in benches:
                tag = f"b{bench['code']}_"
                kind, rows, detail = await _hcservices.fetch_index(
                    client,
                    state_code=target.params["state_code"],
                    bench_code=bench["code"],
                    list_date=list_date,
                    pacer=pacer,
                    today=clock.today(),
                    attempts=attempts,
                )
                if kind == "none_available":
                    none_available += 1
                    total += 1
                    docs.append(
                        RawDoc(
                            doc_key=f"{tag}index", status="not_uploaded", bench_label=bench["name"],
                            list_type="(no list published yet)", error=detail,
                        )
                    )
                    continue
                if kind != "table":
                    if kind == "captcha_failed":
                        captcha_failed += 1
                    total += 1
                    docs.append(
                        RawDoc(
                            doc_key=f"{tag}index", status="fetch_error", bench_label=bench["name"],
                            list_type="(index)", error=f"{kind}: {detail}",
                        )
                    )
                    continue
                total += len(rows)
                take = rows[: max(0, max_docs - len([d for d in docs if d.status == "ok"]))]
                docs.extend(
                    await _hcservices.download_docs(
                        client, take, workdir, pacer=pacer, deadline=deadline, tag=tag
                    )
                )
                for skipped in rows[len(take):]:
                    docs.append(
                        RawDoc(
                            doc_key=f"{tag}{skipped.doc_key}", status="fetch_error",
                            list_type=skipped.list_type, bench_label=skipped.bench_label,
                            error=f"over the {max_docs}-document cap per target",
                        )
                    )
        for d in docs:
            d.meta["parser"] = target.params.get("parser", "")
        if none_available == len(benches):
            return FetchResult(status="none_available", note="no cause list published for this date")
        if captcha_failed == len(benches):
            return FetchResult(status="captcha_failed", error="CAPTCHA budget exhausted")
        return FetchResult(status="ok", docs=docs, doc_total=total)

    # ------------------------------------------------------------------
    def parse(self, doc: RawDoc) -> ParsedDoc:
        from .layouts import parser_for

        family = doc.meta.get("parser") or ""
        parse_fn = parser_for(family)
        if parse_fn is None:
            raise CauseListParseError(f"no parser for layout family {family!r}")
        return parse_fn(doc)


_ADAPTER = None


def get_adapter() -> HCServicesGenericAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = HCServicesGenericAdapter()
    return _ADAPTER
