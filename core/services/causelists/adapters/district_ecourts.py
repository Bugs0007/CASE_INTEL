"""District Courts, every state, via services.ecourts.gov.in.

How this portal publishes cause lists (verified live 2026-10-10, fixtures in
core/tests/fixtures/causelists/district_ecourts/):

  * ONE COURT (one judge) PER REQUEST. `submitCauseList` takes
    `CL_court_no = "<est_code>^<court_no>"` plus civil or criminal (`cicri`),
    behind a CAPTCHA, and answers a JSON envelope whose table HTML is under
    **`case_data`**.
  * Every row prints the CASE'S CNR (in its `viewHistory('..','<CNR>',...)`
    handler), so matching is exact on `Case.cnr_number` -- no case-type alias
    tables.
  * A court with nothing in the chosen mode answers `Record not found`.

Why this is not bharat_courts' `DistrictCourtClient.cause_list()`: it reads
`causelist_data` / `cause_list_data` (the key is `case_data`) and parses
columns the portal doesn't use, so it returns [] for every court -- which
would read as "not listed" for every case. Only its transport, the
project's `_TokenSeedingDistrictClient` session fixes, and the CAPTCHA
solver are reused.

Where the case's court comes from: `Case.court_locator`
(core/services/causelists/locator.py). Without one the hearing is left
alone ("pending") rather than guessed at.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from bs4 import BeautifulSoup

from .. import base, clock, fetchlib
from ..base import (
    PORTAL_DISTRICT,
    CauseListAdapter,
    CauseListEntry,
    FetchResult,
    ListingTarget,
    ParsedDoc,
    RawDoc,
    Resolution,
)
from ..exceptions import CauseListFetchError, CauseListParseError
from ..locator import derive_from_stored
from ..matcher import identity_for_case
from ..normalize import canonical_case_key, normalize_cnr

logger = logging.getLogger(__name__)

KEY = "district_ecourts"
COVERAGE_URL = "https://services.ecourts.gov.in/ecourtindia_v6/?p=cause_list/index"

_VIEW_HISTORY = re.compile(r"viewHistory\('(?P<case_no>[^']*)','(?P<cnr>[A-Za-z0-9]{16})'")
_LISTED_ON = re.compile(r"(Civil|Criminal)\s+Cases\s+Listed\s+on\s*(\d{2}-\d{2}-\d{4})", re.IGNORECASE)
_NO_RECORD = "record not found"


# ---------------------------------------------------------------------------
# Parsing (pure; golden-tested on the real responses)
# ---------------------------------------------------------------------------


def parse_district_list(html: str) -> ParsedDoc:
    """The `case_data` table of one court -> entries.

    Cross-checked against an independent count (`viewHistory(` handlers in
    the raw HTML): a row dropped by the table walk is a parse failure, not a
    shorter list.
    """
    text = (html or "").strip()
    if not text:
        raise CauseListParseError("Empty district cause-list response.")
    handlers = len(_VIEW_HISTORY.findall(text))
    if handlers == 0:
        if _NO_RECORD in text.lower():
            return ParsedDoc(entries=[], list_date=None, genuinely_empty=True)
        raise CauseListParseError(
            "District cause-list response has neither cases nor 'Record not found' -- "
            "the portal's layout may have changed."
        )

    soup = BeautifulSoup(text, "lxml")
    heading = soup.find(id="table_heading")
    heading_lines = [
        re.sub(r"\s+", " ", ln).strip()
        for ln in (heading.get_text("\n") if heading is not None else "").split("\n")
        if ln.strip()
    ]
    list_date = None
    mode = ""
    for ln in heading_lines:
        found = _LISTED_ON.search(ln.replace("\xa0", " "))
        if found:
            mode = found.group(1).lower()
            list_date = datetime.strptime(found.group(2), "%d-%m-%Y").date()
    judge = ""
    designation = ""
    for n, ln in enumerate(heading_lines):
        if ln.lower().startswith("in the court of"):
            judge = ln.split(":", 1)[-1].replace("\xa0", " ").strip()
            designation = heading_lines[n + 1] if n + 1 < len(heading_lines) else ""
            break
    court_name = ", ".join(x for x in (judge, designation) if x)

    table = soup.find("table", id="dispTable") or soup.find("table")
    if table is None:
        raise CauseListParseError("District cause-list response has no table.")
    entries: list[CauseListEntry] = []
    stage = ""
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue
        if len(cells) == 1 or cells[0].get("colspan"):
            label = re.sub(r"\s+", " ", cells[0].get_text(" ")).strip()
            if label:
                stage = label
            continue
        anchor = cells[1].find("a", onclick=True) if len(cells) > 1 else None
        found = _VIEW_HISTORY.search(anchor["onclick"]) if anchor is not None else None
        if found is None:
            continue
        serial = re.sub(r"\D", "", cells[0].get_text()) or "?"
        lines = [re.sub(r"\s+", " ", ln).strip() for ln in cells[1].get_text("\n").split("\n")]
        case_no = next(
            (ln for ln in lines if ln and ln != "View" and not ln.lower().startswith("next hearing")),
            found.group("case_no"),
        )
        entries.append(
            CauseListEntry(
                item_number=serial,
                case_token=case_no,
                cnr=found.group("cnr").upper(),
                court_name=court_name,
                list_type=mode.capitalize(),
                stage=stage,
            )
        )
    if len(entries) != handlers:
        raise CauseListParseError(
            f"Parsed {len(entries)} rows but the page has {handlers} case links -- "
            "refusing a partial district list."
        )
    return ParsedDoc(entries=entries, list_date=list_date)


# ---------------------------------------------------------------------------
# Civil / criminal
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _mode_table() -> dict[str, str]:
    path = Path(__file__).resolve().parent.parent / "data" / "district_case_modes.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    table: dict[str, str] = {}
    for mode_name, mode_code in (("civil", "civ"), ("criminal", "cri")):
        for case_type in raw.get(mode_name, []):
            table[case_type.upper()] = mode_code
    return table


def mode_hint(case) -> str | None:
    """'civ' | 'cri' when the case's type has been SEEN in that mode's real
    lists; None otherwise (the caller then fetches both)."""
    key = canonical_case_key(case.case_number) or canonical_case_key(case.case_number_raw)
    return _mode_table().get(key[0]) if key else None


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------


class DistrictEcourtsAdapter(CauseListAdapter):
    key = KEY
    display_name = "District Courts (eCourts)"
    portal = PORTAL_DISTRICT

    # -- resolve --------------------------------------------------------
    def resolve(self, case) -> Resolution:
        loc = case.court_locator if (case.court_locator or {}).get("kind") == "district" else None
        if loc is None:
            loc = derive_from_stored(case)
        if loc is None:
            return Resolution.pending(
                "Where this case is heard is filled in by its next refresh from the court record", KEY
            )
        if not loc.get("complex_code"):
            return Resolution.pending("The court complex for this case is being worked out", KEY)
        court_value = f"{loc['est_code']}^{loc['court_no']}"
        target = ListingTarget(
            adapter=KEY,
            key=f"{loc['state_code']}/{loc['dist_code']}/{loc['complex_code']}/{court_value}",
            label=f"District court {court_value} (state {loc['state_code']}, district {loc['dist_code']})",
            params={
                "state_code": loc["state_code"],
                "dist_code": loc["dist_code"],
                "complex_code": loc["complex_code"],
                "est_code": loc["est_code"],
                "court_value": court_value,
                "modes": ["civ", "cri"],
                "want_cnrs": [],
            },
        )
        return Resolution.for_target(target)

    def finalize_target(self, target, hearings):
        hints = [mode_hint(h.case) for h in hearings]
        if hints and all(h == "civ" for h in hints):
            modes = ["civ"]  # every case's type has been seen only in civil lists
        elif hints and all(h == "cri" for h in hints):
            modes = ["cri"]
        elif hints.count("cri") > hints.count("civ"):
            modes = ["cri", "civ"]  # unknown types: both, likelier mode first
        else:
            modes = ["civ", "cri"]
        want = sorted({identity_for_case(h.case, KEY).cnr for h in hearings} - {""})
        params = {**target.params, "modes": modes, "want_cnrs": want}
        return ListingTarget(adapter=target.adapter, key=target.key, label=target.label, params=params)

    def target_from_key(self, key: str) -> ListingTarget:
        """'29/2/1290019/2^1' -> a target (for the doctor command)."""
        try:
            state, dist, complex_code, court_value = key.split("/")
            est = court_value.split("^")[0]
        except ValueError as exc:
            raise CauseListFetchError("expected STATE/DIST/COMPLEX/EST^COURT, e.g. 29/2/1290019/2^1") from exc
        return ListingTarget(
            adapter=KEY, key=key, label=f"District court {court_value}",
            params={
                "state_code": state, "dist_code": dist, "complex_code": complex_code,
                "est_code": est, "court_value": court_value, "modes": ["civ", "cri"], "want_cnrs": [],
            },
        )

    def coverage_url(self, case) -> str:
        return COVERAGE_URL

    # -- fetch ----------------------------------------------------------
    def fetch(self, target: ListingTarget, list_date: date, workdir: Path) -> FetchResult:
        budget = float(fetchlib.setting("CAUSE_LIST_DISTRICT_BUDGET_SECONDS", 240))
        try:
            return fetchlib.run_bounded(self._fetch(target, list_date, workdir), budget)
        except CauseListFetchError as exc:
            return FetchResult(status="fetch_error", error=str(exc))
        except Exception as exc:  # noqa: BLE001 -- transport errors etc.
            logger.warning("District cause-list fetch failed: %s: %s", type(exc).__name__, exc)
            return FetchResult(status="fetch_error", error=f"{type(exc).__name__}: {exc}"[:300])

    async def _fetch(self, target: ListingTarget, list_date: date, workdir: Path) -> FetchResult:
        from bharat_courts.districtcourts import endpoints as dc_endpoints
        from bharat_courts.districtcourts.parser import CaptchaError, ServerError
        from core.services.court_data.ecourts_provider import _TokenSeedingDistrictClient

        p = target.params
        pacer = fetchlib.Pacer()
        attempts = int(fetchlib.setting("CAUSE_LIST_CAPTCHA_ATTEMPTS_DISTRICT", 6))
        causelist_date = list_date.strftime("%d-%m-%Y")
        modes: list[str] = list(p.get("modes") or ["civ", "cri"])
        want = {normalize_cnr(c) for c in p.get("want_cnrs", [])} - {""}
        docs: list[RawDoc] = []
        early_exit = False

        async with _TokenSeedingDistrictClient() as client:
            # The court's display label is required by the portal
            # (`court_name_txt`); it comes from the captcha-free dropdown.
            await pacer.wait()
            options = await client.list_cause_list_courts(
                p["state_code"], p["dist_code"], p["complex_code"], p["est_code"]
            )
            label = options.get(p["court_value"])
            if not label:
                return FetchResult(
                    status="fetch_error",
                    error=f"court {p['court_value']} is not in the complex's court list "
                    "(judge reassigned or establishment code changed)",
                )

            for position, mode in enumerate(modes):
                html, problem = None, ""
                for attempt in range(1, attempts + 1):
                    await pacer.wait()
                    await client._init_session()
                    await client._setup_court(
                        state_code=p["state_code"], dist_code=p["dist_code"],
                        court_complex_code=p["complex_code"], est_code=p["est_code"],
                    )
                    captcha = await client._solve_captcha()
                    if not captcha or len(captcha) < 4:
                        problem = "CAPTCHA not readable"
                        continue
                    form = dc_endpoints.cause_list_form(
                        state_code=p["state_code"], dist_code=p["dist_code"],
                        court_complex_code=p["complex_code"], est_code=p["est_code"],
                        court_no=p["court_value"], court_name=label,
                        causelist_date=causelist_date, civil=(mode == "civ"), captcha=captcha,
                    )
                    try:
                        result = await client._post_ajax("cause_list/submitCauseList", form)
                    except CaptchaError:
                        problem = "CAPTCHA rejected"
                        continue
                    except ServerError as exc:
                        problem = str(exc)[:120]
                        if "captcha" in problem.lower():
                            continue
                        break  # a real server complaint: retrying won't change it
                    html = result.get("case_data")
                    if html is None:
                        problem = f"no case_data in response (keys: {sorted(result)[:6]})"
                        continue
                    break
                if html is None:
                    status = "captcha_failed" if "captcha" in problem.lower() else "fetch_error"
                    # A mode we could not read: report what we have, flagged.
                    if not docs:
                        return FetchResult(status=status, error=problem)
                    docs.append(RawDoc(
                        doc_key=f"{p['court_value']}:{mode}", status="fetch_error",
                        list_type="Civil" if mode == "civ" else "Criminal", bench_label=label, error=problem,
                    ))
                    continue

                path = workdir / f"{p['court_value'].replace('^', '_')}_{mode}.html"
                path.write_text(html, encoding="utf-8")
                docs.append(RawDoc(
                    doc_key=f"{p['court_value']}:{mode}", status="ok", path=path,
                    sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(), size=len(html),
                    list_type="Civil" if mode == "civ" else "Criminal", bench_label=label,
                    source_ref=COVERAGE_URL, source_public=False,
                    meta={"court_no": p["court_value"].split("^")[-1], "mode": mode},
                ))
                # Everything we were asked about is already in this list.
                if want and position + 1 < len(modes) and all(cnr in html.upper() for cnr in want):
                    early_exit = True
                    break

        return FetchResult(status="ok", docs=docs, doc_total=len(modes), early_exit=early_exit)

    # -- parse ----------------------------------------------------------
    def parse(self, doc: RawDoc) -> ParsedDoc:
        parsed = parse_district_list(Path(doc.path).read_text(encoding="utf-8"))
        court_no = str(doc.meta.get("court_no") or "")
        if court_no and parsed.entries:
            from dataclasses import replace

            parsed.entries = [replace(e, court_hall=court_no) for e in parsed.entries]
        return parsed


_ADAPTER = None


def get_adapter() -> DistrictEcourtsAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = DistrictEcourtsAdapter()
    return _ADAPTER
