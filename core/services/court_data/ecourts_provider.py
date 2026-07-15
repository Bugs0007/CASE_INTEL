"""
eCourts provider: implements CourtDataProvider on top of bharat-courts.

This is the ONLY module in Case Intel that imports bharat_courts. All the
mechanics below were verified against real services.ecourts.gov.in /
hcservices.ecourts.gov.in responses across two validation spikes before
being ported here as first-party code:

- bharat-courts' public case_status()/case_status_by_party() never
  populate next_hearing_date/status/judges -- that data lives behind a
  case-history endpoint the library defines but never calls
  (hcservices.endpoints.CASE_HISTORY_URL) or never wires a controller
  path for (District Courts' "home/viewHistory" AJAX action, discovered
  by reading the live portal's own components.js).
- HC Services' case-history call additionally needs court_complex_code
  ("0" when there isn't one) and an empty appFlag key -- omitting either
  gets "THERE IS AN ERROR" back, confirmed against the live main.php's
  own inline viewHistory() JS.
- District Courts' case-history call needs a numeric case_no argument
  that is NOT the CNR and is not exposed on CaseInfo -- it's embedded in
  each search result row's onclick="viewHistory(case_no,'CNR',...)"
  attribute and has to be re-extracted from the raw HTML the search
  already returned.
- The live case-history HTML is malformed (the Orders table is missing
  a closing </table> and parses as nested inside the hearing-history
  table) and the hearing-history table must be targeted by its
  "history_table" CSS class, not a header-keyword heuristic (an earlier
  heuristic wrongly matched the details table instead).
- bharat-courts' own CAPTCHA retry (_post_with_captcha_retry) only
  catches the literal "Invalid Captcha" response text. A ServerError
  with Error="ERROR_VAL" -- observed live to sometimes be a
  mis-recognized CAPTCHA failure -- propagates uncaught. The outer retry
  loops in this module catch that too.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime

from bs4 import BeautifulSoup
from django.core.cache import cache

from bharat_courts import DistrictCourtClient, HCServicesClient, get_court, list_all_courts
from bharat_courts.districtcourts import endpoints as dc_endpoints
from bharat_courts.districtcourts.parser import CaptchaError as DistrictCaptchaError
from bharat_courts.districtcourts.parser import ServerError as DistrictServerError
from bharat_courts.districtcourts.parser import parse_case_status_html, parse_complex_value
from bharat_courts.hcservices import endpoints as hc_endpoints
from bharat_courts.hcservices.parser import CaptchaError as HCCaptchaError
from bharat_courts.hcservices.parser import ServerError as HCServerError

from core.services.court_data.base import CourtDataProvider
from core.services.court_data.exceptions import CaptchaSolveError, CaseNotFoundError, CourtPortalError
from core.services.court_data.models import CourtCaseData, HearingRecord

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.5

# Court hierarchy barely ever changes -- cache aggressively via Django's
# cache framework (Redis, already configured for this project) rather
# than hitting the live portal on every form load. A DB table would be
# more discoverable in admin, but caching costs zero migrations/models
# for data that's really just a memoized view of bharat-courts' own
# static registry (list_all_courts()) plus a handful of live dropdown
# calls -- not data Case Intel owns or needs to query relationally.
HIERARCHY_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days
CACHE_KEY_PREFIX = "court_data:hierarchy"


DATE_FORMAT = "%d-%m-%Y"


def _parse_date(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    for fmt in (DATE_FORMAT, "%d-%b-%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip())


_ORDINAL_RE = re.compile(r"(\d+)(st|nd|rd|th)\b", re.I)


def _normalize_ordinal_date(text: str) -> str:
    """'29th December 2023' -> '29 December 2023', parseable by _parse_date."""
    return _ORDINAL_RE.sub(r"\1", text)


_DETAIL_LABELS = {
    "first hearing date": "first_hearing_date",
    "next hearing date": "next_hearing_date",
    "next date": "next_hearing_date",
    "case status": "case_status",
    "nature of disposal": "nature_of_disposal",
    "coram": "court_and_judge",
    "court number and judge": "court_and_judge",
    "case stage": "case_stage",
}


def parse_case_history_html(html: str) -> CourtCaseData | None:
    """Parse an eCourts case-history response into a partial CourtCaseData
    (cnr is filled in by the caller, which already knows it).

    Returns None if the response is empty or an error page -- callers
    treat that as "history unavailable" without failing the whole fetch,
    since case identity/parties are already known from the search step.
    """
    if not html or len(html.strip()) < 20:
        return None
    if "THERE IS AN ERROR" in html or "Invalid Request" in html:
        logger.warning("Case-history endpoint returned an error page: %r", html.strip()[:200])
        return None

    soup = BeautifulSoup(html, "lxml")
    data = CourtCaseData(cnr="")

    # Details table: HC Services renders label+value as <td>; District
    # Courts renders the label as <th scope='row'> -- both are checked.
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) != 2:
            continue
        label = _clean(cells[0].get_text()).lower()
        value = _clean(cells[1].get_text())
        if not label or not value:
            continue
        for key, field_name in _DETAIL_LABELS.items():
            if key in label:
                if field_name in ("next_hearing_date", "first_hearing_date"):
                    parsed = _parse_date(_normalize_ordinal_date(value))
                    if parsed:
                        setattr(data, field_name, parsed)
                elif not getattr(data, field_name):
                    setattr(data, field_name, value)
                break

    # Hearing-history table: match by CSS class, not a header-keyword
    # heuristic (which previously matched the wrong table -- see module
    # docstring).
    table = soup.find("table", class_="history_table")
    if table is None:
        for candidate in soup.find_all("table"):
            if "history" in " ".join(candidate.get("class", [])).lower():
                table = candidate
                break

    if table is not None:
        header_cells = table.find_all("th")
        col_names = [_clean(c.get_text()).lower() for c in header_cells]

        def _col_index(*keywords: str) -> int | None:
            for idx, name in enumerate(col_names):
                if any(kw in name for kw in keywords):
                    return idx
            return None

        idx_causelist = _col_index("cause list")
        idx_judge = _col_index("judge")
        idx_business = _col_index("business")
        idx_hearing = _col_index("hearing date")
        idx_purpose = _col_index("purpose")

        for row in table.find_all("tr"):
            # The live HTML is malformed: the Orders table is missing a
            # closing </table> and parses as nested inside history_table.
            # Skip rows that actually belong to that nested table.
            if row.find_parent("table") is not table:
                continue
            cols = row.find_all("td")
            if not cols or row.find("th"):
                continue
            row_text = [_clean(c.get_text()) for c in cols]

            def _get(idx: int | None) -> str:
                return row_text[idx] if idx is not None and idx < len(row_text) else ""

            hearing = HearingRecord(
                hearing_date=_parse_date(_get(idx_hearing)),
                business_date=_parse_date(_get(idx_business)),
                purpose=_get(idx_purpose),
                judge=_get(idx_judge),
                cause_list_type=_get(idx_causelist),
            )
            if any([hearing.hearing_date, hearing.business_date, hearing.purpose, hearing.judge]):
                data.hearing_history.append(hearing)

    return data


_VIEWHISTORY_RE = re.compile(
    r"viewHistory\((\d+),\s*'([A-Z]{4}\d{12,})'\s*,\s*'?([^,']*)'?\s*,"
    r"\s*'([^']*)'\s*,\s*'([^']*)'\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*'([^']*)'"
)


def _extract_view_history_args(raw_html: str, target_cnr: str) -> dict | None:
    """Recover the numeric case_no District Courts' viewHistory() needs,
    embedded in the search result row's onclick attribute alongside the
    CNR -- not exposed anywhere on CaseInfo."""
    for match in _VIEWHISTORY_RE.finditer(raw_html):
        case_no, cnr, court_code, hideparty, search_flag, state_code, dist_code, complex_code, search_by = match.groups()
        if cnr == target_cnr:
            return {
                "case_no": case_no,
                "cino": cnr,
                "court_code": court_code,
                "hideparty": hideparty,
                "search_flag": search_flag,
                "state_code": state_code,
                "dist_code": dist_code,
                "court_complex_code": complex_code,
                "search_by": search_by,
            }
    return None


def parse_complex_code(raw_value: str) -> tuple[str, str]:
    """Split a list_complexes() dropdown value ("code@est_codes@flag")
    into (complex_code, first_est_code)."""
    complex_code, est_codes, _needs_est = parse_complex_value(raw_value)
    return complex_code, (est_codes[0] if est_codes else "")


class EcourtsProvider(CourtDataProvider):
    """CourtDataProvider backed by bharat-courts against the live eCourts
    portals. Public methods are synchronous; asyncio.run() bridges into
    bharat-courts' async client internally (see case_tracking
    implementation report, Architecture Decisions: v1 is synchronous)."""

    # ------------------------------------------------------------------
    # Public: case fetch
    # ------------------------------------------------------------------

    def fetch_case(self, tracking_config: dict) -> CourtCaseData:
        court_type = tracking_config.get("court_type")
        if court_type == "district":
            return asyncio.run(self._fetch_district(tracking_config))
        if court_type == "high_court":
            return asyncio.run(self._fetch_hc(tracking_config))
        raise ValueError(f"Unknown court_type: {court_type!r}")

    # ------------------------------------------------------------------
    # District Courts
    # ------------------------------------------------------------------

    async def _fetch_district(self, cfg: dict) -> CourtCaseData:
        async with DistrictCourtClient() as client:
            cases, raw_html = await self._district_search_with_retry(client, cfg)
            if not cases:
                raise CaseNotFoundError(
                    "No case found for this case number/year at the selected court. "
                    "Double-check the case type, number, and year."
                )
            case = cases[0]
            result = CourtCaseData(
                cnr=case.cnr_number,
                petitioner=case.petitioner,
                respondent=case.respondent,
                court_name=case.court_name,
            )

            view_args = _extract_view_history_args(raw_html, case.cnr_number)
            if view_args is None:
                logger.warning(
                    "Could not find a viewHistory() link for CNR %s in search results; "
                    "returning case identity without hearing history.",
                    case.cnr_number,
                )
                return result

            history = await self._district_history_with_retry(client, view_args)
            if history is not None:
                history.cnr = case.cnr_number
                history.petitioner = result.petitioner
                history.respondent = result.respondent
                history.court_name = result.court_name
                return history
            return result

    async def _district_search_with_retry(self, client: DistrictCourtClient, cfg: dict):
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                def build_form(captcha: str) -> dict:
                    return dc_endpoints.case_status_by_number_form(
                        state_code=cfg["state_code"],
                        dist_code=cfg["dist_code"],
                        court_complex_code=cfg["court_complex_code"],
                        est_code=cfg.get("est_code", ""),
                        case_type=cfg["case_type"],
                        case_number=cfg["case_number"],
                        year=cfg["year"],
                        captcha=captcha,
                    )

                result = await client._post_with_captcha_retry(
                    "casestatus/submitCaseNo",
                    build_form,
                    state_code=cfg["state_code"],
                    dist_code=cfg["dist_code"],
                    court_complex_code=cfg["court_complex_code"],
                    est_code=cfg.get("est_code", ""),
                )
                html = result.get("case_data", "")
                return parse_case_status_html(html), html
            except (DistrictServerError, DistrictCaptchaError) as exc:
                # bharat-courts' own retry only catches the literal
                # "Invalid Captcha" response text; a generic ServerError
                # (e.g. ERROR_VAL) propagates uncaught -- this outer loop
                # is the fix for that (spike gap #2).
                last_exc = exc
                logger.warning(
                    "District Courts search attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
        if isinstance(last_exc, DistrictCaptchaError):
            raise CaptchaSolveError(f"CAPTCHA solving failed after {MAX_RETRIES} attempts.") from last_exc
        raise CourtPortalError(
            f"District Courts portal error after {MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    async def _district_history_with_retry(self, client: DistrictCourtClient, view_args: dict):
        form = {
            "court_code": view_args["court_code"],
            "state_code": view_args["state_code"],
            "dist_code": view_args["dist_code"],
            "court_complex_code": view_args["court_complex_code"],
            "case_no": view_args["case_no"],
            "cino": view_args["cino"],
            "hideparty": view_args["hideparty"],
            "search_flag": view_args["search_flag"],
            "search_by": view_args["search_by"],
        }
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Reuses the client's own AJAX helper -- app_token rotation
                # and JSON envelope parsing, same as case_status() uses.
                result = await client._post_ajax("home/viewHistory", form)
                html = result.get("data_list", "") or result.get("case_data", "") or ""
                return parse_case_history_html(html)
            except Exception as exc:  # noqa: BLE001 -- history is best-effort, see caller
                last_exc = exc
                logger.warning(
                    "District Courts history attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
        # Non-fatal: the case search already succeeded, so return no
        # history rather than failing the whole fetch.
        logger.error("District Courts history fetch failed after retries: %s", last_exc)
        return None

    # ------------------------------------------------------------------
    # HC Services
    # ------------------------------------------------------------------

    async def _fetch_hc(self, cfg: dict) -> CourtCaseData:
        court = get_court(cfg["hc_court_code"])
        if court is None:
            raise ValueError(f"Unknown hc_court_code: {cfg['hc_court_code']!r}")

        async with HCServicesClient() as client:
            case = await self._hc_search_with_retry(client, court, cfg)
            if case is None:
                raise CaseNotFoundError(
                    "No case found for this case number/year at the selected High Court. "
                    "Double-check the case type, number, and year."
                )
            result = CourtCaseData(
                cnr=case.cnr_number,
                petitioner=case.petitioner,
                respondent=case.respondent,
                court_name=case.court_name,
            )

            history = await self._hc_history_with_retry(client, case, court, cfg)
            if history is not None:
                history.cnr = case.cnr_number
                history.petitioner = result.petitioner
                history.respondent = result.respondent
                history.court_name = result.court_name
                return history
            return result

    async def _hc_search_with_retry(self, client: HCServicesClient, court, cfg: dict):
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                cases = await client.case_status(
                    court,
                    case_type=cfg["case_type"],
                    case_number=cfg["case_number"],
                    year=cfg["year"],
                    bench_code=cfg.get("bench_code", "1"),
                )
                return cases[0] if cases else None
            except (HCServerError, HCCaptchaError) as exc:
                # Same gap as District Courts -- bharat-courts' internal
                # retry doesn't catch a generic ServerError.
                last_exc = exc
                logger.warning("HC Services search attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
        if isinstance(last_exc, HCCaptchaError):
            raise CaptchaSolveError(f"CAPTCHA solving failed after {MAX_RETRIES} attempts.") from last_exc
        raise CourtPortalError(f"HC Services portal error after {MAX_RETRIES} attempts: {last_exc}") from last_exc

    async def _hc_history_with_retry(self, client: HCServicesClient, case, court, cfg: dict):
        if not case.cnr_number or not case.filing_number:
            logger.warning(
                "HC Services case %s missing cnr_number/filing_number needed for history fetch.",
                case.case_number,
            )
            return None

        form = {
            "cino": case.cnr_number,
            "case_no": case.filing_number,
            "state_code": court.state_code,
            "court_code": cfg.get("bench_code", "1"),
            "court_complex_code": "0",
            "appFlag": "",
        }
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client._http.post(
                    hc_endpoints.CASE_HISTORY_URL,
                    data=form,
                    headers={"Referer": hc_endpoints.MAIN_PAGE_URL},
                )
                return parse_case_history_html(resp.text)
            except Exception as exc:  # noqa: BLE001 -- history is best-effort, see caller
                last_exc = exc
                logger.warning("HC Services history attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
        logger.error("HC Services history fetch failed after retries: %s", last_exc)
        return None

    # ------------------------------------------------------------------
    # Court hierarchy discovery (cached -- changes ~never)
    # ------------------------------------------------------------------

    def _cached(self, key_parts: tuple, fn):
        key = ":".join([CACHE_KEY_PREFIX, *[str(p) for p in key_parts]])
        value = cache.get(key)
        if value is not None:
            return value
        value = fn()
        cache.set(key, value, HIERARCHY_CACHE_TTL)
        return value

    def list_court_options(self, court_type: str) -> dict[str, str]:
        if court_type == "district":
            return self._cached(
                ("district_states",),
                lambda: asyncio.run(self._list_district_states()),
            )
        if court_type == "high_court":
            return self._cached(
                ("hc_courts",),
                lambda: {c.code: c.name for c in list_all_courts() if c.court_type.value == "high_court"},
            )
        raise ValueError(f"Unknown court_type: {court_type!r}")

    async def _list_district_states(self) -> dict[str, str]:
        async with DistrictCourtClient() as client:
            return await client.list_states()

    def list_districts(self, state_code: str) -> dict[str, str]:
        return self._cached(
            ("districts", state_code),
            lambda: asyncio.run(self._list_districts(state_code)),
        )

    async def _list_districts(self, state_code: str) -> dict[str, str]:
        async with DistrictCourtClient() as client:
            return await client.list_districts(state_code)

    def list_complexes(self, state_code: str, dist_code: str) -> dict[str, str]:
        return self._cached(
            ("complexes", state_code, dist_code),
            lambda: asyncio.run(self._list_complexes(state_code, dist_code)),
        )

    async def _list_complexes(self, state_code: str, dist_code: str) -> dict[str, str]:
        async with DistrictCourtClient() as client:
            return await client.list_complexes(state_code, dist_code)

    def list_benches(self, hc_court_code: str) -> dict[str, str]:
        return self._cached(
            ("benches", hc_court_code),
            lambda: asyncio.run(self._list_benches(hc_court_code)),
        )

    async def _list_benches(self, hc_court_code: str) -> dict[str, str]:
        court = get_court(hc_court_code)
        if court is None:
            raise ValueError(f"Unknown hc_court_code: {hc_court_code!r}")
        async with HCServicesClient() as client:
            return await client.list_benches(court)

    def list_case_types(self, court_type: str, **hierarchy) -> dict[str, str]:
        if court_type == "district":
            key = ("district_case_types", hierarchy["state_code"], hierarchy["dist_code"],
                   hierarchy["court_complex_code"], hierarchy.get("est_code", ""))
            return self._cached(key, lambda: asyncio.run(self._list_district_case_types(hierarchy)))
        if court_type == "high_court":
            key = ("hc_case_types", hierarchy["hc_court_code"], hierarchy.get("bench_code", "1"))
            return self._cached(key, lambda: asyncio.run(self._list_hc_case_types(hierarchy)))
        raise ValueError(f"Unknown court_type: {court_type!r}")

    async def _list_district_case_types(self, hierarchy: dict) -> dict[str, str]:
        async with DistrictCourtClient() as client:
            return await client.list_case_types(
                hierarchy["state_code"],
                hierarchy["dist_code"],
                hierarchy["court_complex_code"],
                hierarchy.get("est_code", ""),
            )

    async def _list_hc_case_types(self, hierarchy: dict) -> dict[str, str]:
        court = get_court(hierarchy["hc_court_code"])
        if court is None:
            raise ValueError(f"Unknown hc_court_code: {hierarchy['hc_court_code']!r}")
        async with HCServicesClient() as client:
            return await client.list_case_types(court, bench_code=hierarchy.get("bench_code", "1"))
