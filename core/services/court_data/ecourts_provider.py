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

CNR search (fetch_case_by_cnr, added after the above -- not covered by
either original spike, which only exercised bharat-courts' own case-
number/party-name methods, never the portals' own CNR search pages):

- Neither portal's CNR search is implemented anywhere in bharat-courts
  (grepped the installed package; zero hits for cnr_status or a CNR
  search action_code). Both were found by fetching the live pages
  directly and reading their embedded JS (no browser devtools available).
- District Courts: the CNR form lives on the portal's home page
  (?p=home/index, not ?p=cnr_status/index -- that path renders an empty
  shell), submitting via searchByCNR.js to POST cnr_status/searchByCNR
  with just {cino, fcaptcha_code}. No court hierarchy / set_data call
  needed -- confirmed live, a bare CNR + solved CAPTCHA is sufficient.
- HC Services: the CNR form's funViewCinoHistory() (inline in main.php)
  POSTs to the same index_qry.php used by showRecords, with
  action_code=fetchStateDistCourtNew & caseStatusSearchType=CNRNumber.
  Also confirmed live to need no High Court / bench pre-selection.
- Both responses are strictly BETTER than the cascade path's: a single
  call returns case details, current status, parties, AND the full
  hearing-history table together (District's casetype_list / HC's raw
  HTML both already contain a "history_table"-classed table) -- no
  second viewHistory/case-history call needed at all.
- Neither portal's JSON/text envelope reliably flags "not found" the way
  the module docstring's ERROR_VAL handling does. District's status key
  was observed to stay 1 even for a CNR proven not to exist -- the only
  reliable signal is the literal "This Case Code does not exists" text
  in casetype_list. HC's not-found signal is "THERE IS AN SQL ERROR" in
  the response body; a rejected CAPTCHA there instead shows "ERROR_VAL"
  (the same portal-side error variable name already handled for
  showRecords -- confirmed by reading main.php's searchForError var).

Advocate search (search_by_advocate, added for advocate onboarding --
District Courts only so far; HC Services' equivalent hasn't been spiked):

- Neither bharat-courts nor this module's own CNR-search work covers
  advocate-name/bar-code search -- confirmed by grepping the installed
  package (no case_status_by_advocate, no advocate endpoint helper in
  districtcourts.endpoints). Discovered live by fetching
  services.ecourts.gov.in/ecourtindia_v6/?p=casestatus/index directly and
  its js/searchByCaseStatus.js (submit_adv_name()).
- The portal's "Search by Advocate" tab (form id frm_adv_search_name)
  POSTs to casestatus/submitAdvName -- a sibling of submitPartyName/
  submitCaseNo, same JSON envelope shape ({status, div_captcha, adv_data}).
- Two sub-modes selected by radAdvt: "1" = Advocate Name (field
  advocate_name, min 3 chars per the page's own help text), "2" = Bar
  Code -- submitted as THREE SEPARATE fields (adv_bar_state, adv_bar_code,
  adv_bar_year), not one combined "STATE/NUMBER/YEAR" string; a bar code
  argument here must be split on "/" before submitting.
- case_status (Pending/Disposed/Both) is accepted same as party-name
  search, but there is NO case-registration-year field for this search
  mode at all -- confirmed by reading the live form HTML and its
  client-side validation (validate_adv_name()), not assumed. This means a
  single search call already returns everything; no year-range looping
  is needed (unlike an earlier plan draft that assumed party-name
  search's mandatory year requirement would carry over here).
- The captcha field is named adv_bar_captcha... actually adv_captcha_code
  -- a different name than fcaptcha_code (party/CNR) or case_captcha_code
  (case-number search). Reuses the same generic captcha-image/OCR flow
  (_solve_captcha()), just posted under this field's name.
- Reuses parse_case_status_html for the adv_data payload -- same
  results-grid shape the party-name/case-number searches already produce
  (auto-detected 4- or 7-column format).

The "Invalid Request" bug that broke list_districts() (and every other
District Courts AJAX call) was root-caused and FIXED 24 Jul 2026. It was
two independent missing pieces, both handled by _TokenSeedingDistrictClient
below (see its block comment): (1) bharat-courts sent an empty app_token
because its _init_session GETs the tokenless home page, and (2) nothing
sent the per-session "delimeter" header the portal validates on every AJAX
POST. With both fixed, list_districts / list_complexes / search_by_advocate
were all verified live returning real data (41 Maharashtra districts, real
advocate-search results). It was never a WAF/IP/TLS-fingerprint block -- a
byte-and-fingerprint-faithful replay confirmed the server rejects on the
missing delimeter at the application layer, identically from two different
source IPs.

OPEN ISSUE, found 14 Aug 2026: list_districts()/list_complexes() (via
fillDistrict) were re-confirmed to have the CORRECT client wiring
(_TokenSeedingDistrictClient, same as search_by_advocate -- verified by
reading the code, not assumed) and were still crashing requests/jobs with
an unhandled exception -- fixed below via _run_hierarchy_call(), which
converts any failure here into CourtPortalError/CaptchaSolveError instead
of propagating raw. BUT a live re-test of list_districts('1') the same day
showed the portal STILL rejecting fillDistrict with the identical "Invalid
Request" message, despite a freshly-seeded real app_token and the correct
live delimeter both confirmed present on the request. So the 24 Jul fix
above is no longer (or was never fully) sufficient for THIS endpoint
specifically -- district/complex listing now fails cleanly (CourtPortalError
-> 502) instead of crashing, but does not yet actually return real data.
Root-causing that is unstarted -- couldn't triangulate further without
either an OCR captcha solver configured (to compare against a known-still-
working captcha endpoint live) or a fresh byte-level diff against the
portal's current session/JS behavior, comparable in effort to the original
24 Jul spike. Flagged and deliberately deferred rather than guessed at.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx
from django.core.cache import cache

from bharat_courts import CaseInfo, DistrictCourtClient, HCServicesClient, get_court, list_all_courts
from bharat_courts.districtcourts import endpoints as dc_endpoints
from bharat_courts.districtcourts.parser import CaptchaError as DistrictCaptchaError
from bharat_courts.districtcourts.parser import ServerError as DistrictServerError
from bharat_courts.districtcourts.parser import parse_case_status_html
from bharat_courts.hcservices import endpoints as hc_endpoints
from bharat_courts.hcservices.parser import CaptchaError as HCCaptchaError
from bharat_courts.hcservices.parser import ServerError as HCServerError

from core.services.court_data.base import CourtDataProvider
from core.services.court_data.ecourts_parsing import (
    _DC_ORDERS_BASE,
    _HC_ORDERS_BASE,
    _district_advocate_search_form,
    _extract_view_history_args,
    _parse_district_orders,
    _parse_hc_orders,
    _strip_pdf_prefix,
    parse_case_history_html,
    split_bar_code,
)
from core.services.court_data.exceptions import (
    CaptchaSolveError,
    CaseNotFoundError,
    CourtDataError,
    CourtPortalError,
)
from core.services.court_data.models import CourtCaseData, CourtOrderRecord

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.5

# Advocate search gets more attempts than MAX_RETRIES (used by CNR/case-
# number/party search): root-caused 25 Jul 2026 that bharat-courts'
# _post_with_captcha_retry effectively delivered only ONE real captcha
# attempt per outer retry here (see _district_search_by_advocate's
# docstring) rather than its apparent 5, so the real budget was thinner
# than intended. Now that each attempt is spent correctly (see below), a
# higher count buys real additional captcha tries at low cost -- solving
# is the dominant failure mode for this endpoint specifically.
ADVOCATE_SEARCH_MAX_ATTEMPTS = 6


# ---------------------------------------------------------------------------
# Token-seeding + delimeter District Courts client
#
# The District Courts portal rejected EVERY bharat-courts AJAX POST
# (fillDistrict, fillcomplex, submitCaseNo, submitAdvName, searchByCNR, ...)
# with the JSON "Invalid Request" error. Root-caused live 24 Jul 2026 by
# capturing the outgoing requests and diffing them byte-for-byte against the
# portal's own dropdown JS. TWO independent things were missing:
#
# 1. A real app_token. bharat-courts 0.3.0's _init_session() GETs the bare
#    BASE_URL + "/" home page, which renders NO #app_token hidden field, so
#    every POST went out with app_token="" (captured:
#    `state_code=1&ajax_req=true&app_token=`). The casestatus/index page DOES
#    render a session-bound #app_token -- seed from there. A cold GET of that
#    page is enough; the token does not need the browser's home->casestatus
#    "arming" navigation (verified live).
#
# 2. A "delimeter" request header. The portal's own ajaxCall() (components.js)
#    sends `headers: {delimeter: <value>, abc: "xyz"}` on EVERY AJAX POST,
#    where <value> is a string baked into components.js that the server
#    validates. It is NOT constant -- it rotates per session/deploy (observed
#    changing between fetches: "1bsav864y624e" -> "19873bsav864y624etp" ->
#    "vmgasjnn98dsf846"), so it must be scraped live from the components.js
#    the current session is served, not hardcoded. Without it the server
#    returns "Invalid Request" even with a perfect token. This is the piece
#    that made byte-and-TLS-faithful replays (httpx, curl, curl_cffi Chrome
#    impersonation) all fail until it was found -- it is an application-level
#    check, not a WAF/IP/fingerprint block (two different source IPs, dev box
#    and EC2, behaved identically).
#
# _init_session below does both: scrapes the live delimeter and pins it (plus
# the static abc=xyz) as default headers on the shared httpx client so every
# subsequent bharat-courts POST carries them, then seeds the app_token. This
# repairs every District Courts operation at once, since they all funnel
# through _init_session().
# ---------------------------------------------------------------------------

_APP_TOKEN_RE = re.compile(r"""id=['"]app_token['"]\s+value=["']([0-9a-f]+)["']""")
_DELIMETER_RE = re.compile(r'var\s+delimeter\s*=\s*"([^"]+)"')
_TOKEN_SEED_URL = f"{dc_endpoints.BASE_URL}/?p=casestatus/index"
_COMPONENTS_JS_URL = f"{dc_endpoints.BASE_URL}/js/components.js"


class _TokenSeedingDistrictClient(DistrictCourtClient):
    """DistrictCourtClient whose _init_session (a) pins the live 'delimeter'
    anti-scraping header the portal validates on every AJAX POST, and (b)
    seeds a real app_token from the casestatus/index page -- the vendored
    client does neither, so every District Courts POST got "Invalid Request"
    (see the block comment above)."""

    async def _init_session(self) -> None:
        # (a) Scrape the current delimeter from components.js and pin it (plus
        # the static abc=xyz) as default headers on the shared httpx client,
        # so every subsequent bharat-courts _post_ajax carries them. The value
        # rotates, so it must be read live from the same session that will POST.
        try:
            js = await self._http.get(_COMPONENTS_JS_URL)
            delim = _DELIMETER_RE.search(js.text)
            if delim:
                client = self._http._ensure_client()  # underlying httpx.AsyncClient
                client.headers["delimeter"] = delim.group(1)
                client.headers["abc"] = "xyz"
            else:
                logger.warning("Could not find delimeter in %s; POSTs may be rejected.", _COMPONENTS_JS_URL)
        except Exception:  # noqa: BLE001 -- delimeter is best-effort; token seed still runs
            logger.warning("Failed to fetch/parse delimeter from %s.", _COMPONENTS_JS_URL, exc_info=True)

        # (b) Seed the app_token from the casestatus page (not the tokenless
        # home page the vendored client uses).
        resp = await self._http.get(
            _TOKEN_SEED_URL, headers={"Referer": f"{dc_endpoints.BASE_URL}/"}
        )
        match = _APP_TOKEN_RE.search(resp.text)
        if match:
            self._app_token = match.group(1)
        else:
            # Page shape changed -- fall back to the vendored bootstrap
            # rather than silently leaving the token unset.
            logger.warning(
                "Could not seed app_token from %s; falling back to vendored init_session.",
                _TOKEN_SEED_URL,
            )
            await super()._init_session()

# Court hierarchy barely ever changes -- cache aggressively via Django's
# cache framework (LocMemCache, already configured for this project) rather
# than hitting the live portal on every form load. A DB table would be
# more discoverable in admin, but caching costs zero migrations/models
# for data that's really just a memoized view of bharat-courts' own
# static registry (list_all_courts()) plus a handful of live dropdown
# calls -- not data Case Intel owns or needs to query relationally.
HIERARCHY_CACHE_TTL = 60 * 60 * 24 * 30  # 30 days
CACHE_KEY_PREFIX = "court_data:hierarchy"

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
        if court_type not in ("district", "high_court"):
            raise ValueError(f"Unknown court_type: {court_type!r}")

        # CNR-first dispatch: a tracking_config carrying "cnr" (the setup
        # form's primary path, see fetch_case_by_cnr) needs no court
        # hierarchy / case_type/case_number/year at all. Handling this here
        # rather than only in fetch_case_by_cnr means refresh_case_tracking
        # -- which only ever calls fetch_case(case.tracking_config) --
        # re-fetches CNR-based cases correctly with no changes of its own.
        cnr = tracking_config.get("cnr")
        if cnr:
            return self.fetch_case_by_cnr(cnr, court_type)

        if court_type == "district":
            return asyncio.run(self._fetch_district(tracking_config))
        return asyncio.run(self._fetch_hc(tracking_config))

    def fetch_case_by_cnr(self, cnr: str, court_type: str) -> CourtCaseData:
        if court_type == "district":
            return asyncio.run(self._fetch_district_by_cnr(cnr))
        if court_type == "high_court":
            return asyncio.run(self._fetch_hc_by_cnr(cnr))
        raise ValueError(f"Unknown court_type: {court_type!r}")

    # ------------------------------------------------------------------
    # Public: advocate search (District Courts only -- see module docstring)
    # ------------------------------------------------------------------

    def search_by_advocate(
        self,
        hierarchy: dict,
        *,
        advocate_name: str = "",
        bar_code: str = "",
        status_filter: str = "Both",
    ) -> list[CaseInfo]:
        """Search District Courts cases by advocate name or bar code.

        Exactly one of advocate_name (min 3 chars, partial match per the
        portal's own help text) or bar_code ("STATE/NUMBER/YEAR", e.g.
        "MAH/1234/2015") must be given. No case-registration-year filter
        exists for this search mode -- a single call already returns every
        matching case for the given status_filter ("Pending"/"Disposed"/
        "Both"), unlike case-number/party-name search.

        hierarchy: {state_code, dist_code, court_complex_code, est_code?}.

        Raises ValueError if neither/both of advocate_name/bar_code are
        given, or bar_code doesn't match the expected format. Raises
        CaseNotFoundError/CourtPortalError/CaptchaSolveError as usual.
        """
        if bool(advocate_name) == bool(bar_code):
            raise ValueError("Exactly one of advocate_name or bar_code must be given.")
        bar_state = bar_year = ""
        if bar_code:
            bar_state, bar_code, bar_year = split_bar_code(bar_code)
        return asyncio.run(
            self._district_search_by_advocate(
                hierarchy,
                advocate_name=advocate_name,
                bar_state=bar_state,
                bar_code=bar_code,
                bar_year=bar_year,
                status_filter=status_filter,
            )
        )

    # ------------------------------------------------------------------
    # Public: orders (Phase B)
    # ------------------------------------------------------------------

    def list_orders(self, tracking_config: dict) -> list[CourtOrderRecord]:
        cnr, court_type = self._order_identity(tracking_config)
        if court_type == "district":
            return asyncio.run(self._list_district_orders(cnr))
        return asyncio.run(self._list_hc_orders(cnr))

    def download_order(self, tracking_config: dict, order: CourtOrderRecord) -> bytes:
        cnr, court_type = self._order_identity(tracking_config)
        if court_type == "district":
            return asyncio.run(self._download_district_order(cnr, order))
        return asyncio.run(self._download_hc_order(cnr, order))

    @staticmethod
    def _order_identity(tracking_config: dict) -> tuple[str, str]:
        court_type = tracking_config.get("court_type")
        if court_type not in ("district", "high_court"):
            raise ValueError(f"Unknown court_type: {court_type!r}")
        cnr = tracking_config.get("cnr")
        if not cnr:
            raise ValueError(
                "Order listing needs a CNR in tracking_config -- callers "
                "should inject case.cnr_number for cascade-shaped configs."
            )
        return cnr, court_type

    async def _list_hc_orders(self, cnr: str) -> list[CourtOrderRecord]:
        async with HCServicesClient() as client:
            html = await self._hc_cnr_search(client, cnr)
            return [record for record, _href in _parse_hc_orders(html, cnr)]

    async def _download_hc_order(self, cnr: str, order: CourtOrderRecord) -> bytes:
        async with HCServicesClient() as client:
            # Fresh search in THIS session -- the display_pdf.php link is
            # session-bound (spike-verified), so a stored href is useless.
            html = await self._hc_cnr_search(client, cnr)
            for record, href in _parse_hc_orders(html, cnr):
                if record.dedup_key != order.dedup_key:
                    continue
                url = _HC_ORDERS_BASE + href.lstrip("/")
                resp = await client._http.get(
                    url, headers={"Referer": hc_endpoints.MAIN_PAGE_URL}
                )
                raw = _strip_pdf_prefix(resp.content)
                if raw[:5] != b"%PDF-":
                    raise CourtPortalError(
                        f"HC Services order download did not return a PDF "
                        f"(first bytes: {resp.content[:80]!r})"
                    )
                return raw
            raise CaseNotFoundError(
                f"Order {order.dedup_key!r} no longer listed for CNR {cnr!r} on HC Services."
            )

    async def _list_district_orders(self, cnr: str) -> list[CourtOrderRecord]:
        async with _TokenSeedingDistrictClient() as client:
            html = await self._district_cnr_search(client, cnr)
            return [record for record, _args in _parse_district_orders(html, cnr)]

    async def _download_district_order(self, cnr: str, order: CourtOrderRecord) -> bytes:
        async with _TokenSeedingDistrictClient() as client:
            html = await self._district_cnr_search(client, cnr)
            for record, args in _parse_district_orders(html, cnr):
                if record.dedup_key != order.dedup_key:
                    continue
                # Two-step download, per the live portal's own displayPdf()
                # JS: POST home/display_pdf -> JSON with a relative path ->
                # GET that path in the same session.
                resp = await client._post_ajax("home/display_pdf", args)
                order_path = resp.get("order", "")
                if not order_path:
                    raise CourtPortalError(
                        f"District Courts display_pdf returned no file path: {str(resp)[:300]!r}"
                    )
                r2 = await client._http.get(_DC_ORDERS_BASE + order_path.lstrip("/"))
                raw = _strip_pdf_prefix(r2.content)
                if raw[:5] != b"%PDF-":
                    raise CourtPortalError(
                        f"District Courts order download did not return a PDF "
                        f"(first bytes: {r2.content[:80]!r})"
                    )
                return raw
            raise CaseNotFoundError(
                f"Order {order.dedup_key!r} no longer listed for CNR {cnr!r} on the District Courts portal."
            )

    # ------------------------------------------------------------------
    # District Courts
    # ------------------------------------------------------------------

    async def _fetch_district(self, cfg: dict) -> CourtCaseData:
        async with _TokenSeedingDistrictClient() as client:
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

    async def _district_search_by_advocate(
        self,
        hierarchy: dict,
        *,
        advocate_name: str,
        bar_state: str,
        bar_code: str,
        bar_year: str,
        status_filter: str,
    ) -> list[CaseInfo]:
        """Hand-rolled retry loop (matches _district_cnr_search's existing
        pattern in this file) instead of bharat-courts' own
        _post_with_captcha_retry. Root-caused live 25 Jul 2026 -- two real
        bugs in the vendored path, both fixed here:

        1. casestatus/submitAdvName's "Invalid Captcha" response body has
           errormsg populated (confirmed live: {"errormsg":"Invalid
           Captcha... ", "div_captcha": ...}), so bharat-courts' own
           parse_ajax_response raises ServerError for it -- NOT CaptchaError
           (that only fires when status==0 with no errormsg key, a
           different response shape). _post_with_captcha_retry's inner loop
           only catches CaptchaError, so a wrong-captcha response propagated
           straight out on the FIRST sub-attempt, uncaught by its own 5-try
           budget. Net effect: every "advocate search attempt N/3" in the
           old code was exactly ONE real network attempt, not up to 5 --
           the retry depth the code's structure implied was never actually
           delivered.
        2. A blank/wrong-length OCR decode (ddddocr correctly refuses to
           return a non-6-char result -- see bharat_courts.captcha.ocr) was
           still being SUBMITTED as adv_captcha_code="" instead of silently
           refetching a new image, burning one of the (already-thin) real
           attempts on a guaranteed-fail guess.

        Fetching the client's own primitives directly here (matching
        _district_cnr_search) fixes both: only CaptchaSolveError-worthy
        blank decodes skip the network round-trip entirely (fix #2), and
        this method's own except clause -- same as the rest of this file --
        already catches both DistrictServerError and DistrictCaptchaError
        uniformly, so misclassification no longer matters (fix #1).
        ADVOCATE_SEARCH_MAX_ATTEMPTS (6) is used instead of the shared
        MAX_RETRIES (3, used by CNR/case-number/party search) since a
        correctly-spent attempt is now the norm and captcha-solving is the
        dominant cost/failure mode specifically on this endpoint.

        Also treats an empty adv_data (status==1, no error) as a portal
        error rather than silently returning zero results -- confirmed live
        that submitting without BOTH a real dist_code AND a real
        court_complex_code returns HTTP 200 with a genuinely blank body,
        indistinguishable from "no matching cases" unless checked for.
        """
        async with _TokenSeedingDistrictClient() as client:
            last_exc: Exception | None = None
            for attempt in range(1, ADVOCATE_SEARCH_MAX_ATTEMPTS + 1):
                await client._init_session()
                await client._setup_court(
                    state_code=hierarchy["state_code"],
                    dist_code=hierarchy["dist_code"],
                    court_complex_code=hierarchy["court_complex_code"],
                    est_code=hierarchy.get("est_code", ""),
                )
                captcha = await client._solve_captcha()
                if not captcha:
                    last_exc = CaptchaSolveError("OCR failed to read the CAPTCHA image.")
                    logger.warning(
                        "District Courts advocate search attempt %d/%d: OCR could not "
                        "read a valid CAPTCHA, refetching without submitting.",
                        attempt, ADVOCATE_SEARCH_MAX_ATTEMPTS,
                    )
                    if attempt < ADVOCATE_SEARCH_MAX_ATTEMPTS:
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue

                form = _district_advocate_search_form(
                    state_code=hierarchy["state_code"],
                    dist_code=hierarchy["dist_code"],
                    court_complex_code=hierarchy["court_complex_code"],
                    est_code=hierarchy.get("est_code", ""),
                    advocate_name=advocate_name,
                    bar_state=bar_state,
                    bar_code=bar_code,
                    bar_year=bar_year,
                    status_filter=status_filter,
                    captcha=captcha,
                )
                try:
                    result = await client._post_ajax("casestatus/submitAdvName", form)
                except (DistrictServerError, DistrictCaptchaError) as exc:
                    last_exc = exc
                    logger.warning(
                        "District Courts advocate search attempt %d/%d failed: %s",
                        attempt, ADVOCATE_SEARCH_MAX_ATTEMPTS, exc,
                    )
                    if attempt < ADVOCATE_SEARCH_MAX_ATTEMPTS:
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue
                except httpx.HTTPError as exc:
                    # Network/transport-level failure -- NOT an HTTP status
                    # error (those are on the response, this is on reading
                    # it), so bharat-courts' own parser never sees it.
                    # Observed live 26 Jul 2026: a very common advocate name
                    # can make the portal's own adv_data response body
                    # enormous (one real case: 25.7MB), and the connection
                    # gets cut mid-body (httpx.RemoteProtocolError, "peer
                    # closed connection ... received 8912896 bytes, expected
                    # 25698031") -- this is portal/network flakiness on a
                    # huge payload, not a captcha or request-shape problem,
                    # so it goes through the SAME per-attempt retry as
                    # everything else here rather than crashing the whole
                    # district/state run uncaught.
                    last_exc = exc
                    logger.warning(
                        "District Courts advocate search attempt %d/%d: network/transport "
                        "error (%s: %s).",
                        attempt, ADVOCATE_SEARCH_MAX_ATTEMPTS, type(exc).__name__, exc,
                    )
                    if attempt < ADVOCATE_SEARCH_MAX_ATTEMPTS:
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue

                html = result.get("adv_data", "")
                if not html:
                    last_exc = CourtPortalError(
                        "District Courts advocate search returned an empty response -- "
                        "dist_code/court_complex_code must both be a real, valid district "
                        "and court complex (verified live: leaving either empty/0 returns "
                        "HTTP 200 with a blank body, not an error)."
                    )
                    logger.warning(
                        "District Courts advocate search attempt %d/%d: empty adv_data "
                        "(missing/invalid dist_code or court_complex_code).",
                        attempt, ADVOCATE_SEARCH_MAX_ATTEMPTS,
                    )
                    if attempt < ADVOCATE_SEARCH_MAX_ATTEMPTS:
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                    continue

                return parse_case_status_html(html)

            if isinstance(last_exc, (DistrictCaptchaError, CaptchaSolveError)):
                raise CaptchaSolveError(
                    f"CAPTCHA solving failed after {ADVOCATE_SEARCH_MAX_ATTEMPTS} attempts."
                ) from last_exc
            raise CourtPortalError(
                f"District Courts advocate search failed after {ADVOCATE_SEARCH_MAX_ATTEMPTS} "
                f"attempts: {last_exc}"
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

    async def _fetch_district_by_cnr(self, cnr: str) -> CourtCaseData:
        """CNR search on the District Courts portal (Part 1 investigation).

        A single POST to cnr_status/searchByCNR (found in the portal's own
        searchByCNR.js, undocumented by bharat-courts) returns case
        details, current status, AND the full hearing-history table in one
        response -- no court hierarchy selection and no separate
        home/viewHistory call needed, unlike fetch_case's cascade path.

        The endpoint doesn't reliably signal "not found" via the JSON
        envelope's status field (observed to stay 1 even for a
        provably-nonexistent CNR in testing) -- the only reliable
        not-found signal is the literal "This Case Code does not exists"
        message in casetype_list, checked for below.
        """
        async with _TokenSeedingDistrictClient() as client:
            html = await self._district_cnr_search(client, cnr)
            data = parse_case_history_html(html)
            if data is None:
                raise CaseNotFoundError(f"No case found for CNR {cnr!r} on the District Courts portal.")
            data.cnr = cnr
            return data

    async def _district_cnr_search(self, client: DistrictCourtClient, cnr: str) -> str:
        """Run the District Courts CNR search and return the raw
        casetype_list HTML. Shared by _fetch_district_by_cnr and the
        order-listing/download path (Phase B)."""
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            await client._init_session()
            captcha = await client._solve_captcha()
            if not captcha:
                last_exc = CaptchaSolveError("OCR failed to read the CAPTCHA image.")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            try:
                result = await client._post_ajax(
                    "cnr_status/searchByCNR",
                    {"cino": cnr, "fcaptcha_code": captcha},
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "District Courts CNR search attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            html = result.get("casetype_list", "")
            if "does not exist" in html.lower():
                raise CaseNotFoundError(f"No case found for CNR {cnr!r} on the District Courts portal.")
            if result.get("status") == 0:
                # Portal rejected the CAPTCHA and cleared the form.
                last_exc = CaptchaSolveError("District Courts portal rejected the CAPTCHA.")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            if "history_table" not in html:
                # Unrecognized response shape -- neither the known
                # not-found message nor a real result. Don't guess;
                # surface it as a portal error with the raw content.
                last_exc = CourtPortalError(
                    f"Unrecognized response from District Courts CNR search: {html[:300]!r}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            return html

        if isinstance(last_exc, CaptchaSolveError):
            raise last_exc
        raise CourtPortalError(
            f"District Courts CNR search failed after {MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

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

    async def _fetch_hc_by_cnr(self, cnr: str) -> CourtCaseData:
        """CNR search on the HC Services portal (Part 1 investigation).

        POSTs directly to index_qry.php with action_code=fetchStateDistCourtNew
        & caseStatusSearchType=CNRNumber (found in the portal's own inline
        funViewCinoHistory() JS on main.php, undocumented by bharat-courts).
        Confirmed live: works with NO High Court / bench pre-selection --
        the CNR alone is enough, and the server-rendered page returned
        already contains the full hearing history (class="history_table"),
        same single-call shape as the District Courts CNR search.

        Response is a raw HTML page, not the JSON envelope showRecords()
        uses, so error detection is substring-based against two confirmed
        live signals: "THERE IS AN SQL ERROR" for a genuinely nonexistent
        CNR, and "ERROR_VAL" (the portal's own JS error variable name,
        matching the ERROR_VAL ServerError this module already handles
        for showRecords) for a rejected CAPTCHA / generic server error.
        """
        async with HCServicesClient() as client:
            text = await self._hc_cnr_search(client, cnr)
            data = parse_case_history_html(text)
            if data is None:
                raise CaseNotFoundError(f"No case found for CNR {cnr!r} on the HC Services portal.")
            data.cnr = cnr
            return data

    async def _hc_cnr_search(self, client: HCServicesClient, cnr: str) -> str:
        """Run the HC Services CNR search and return the raw HTML page.

        Shared by _fetch_hc_by_cnr and the order-listing/download path
        (Phase B) -- the same single response carries the case details,
        history_table, AND the order_table with its session-bound
        display_pdf.php links.
        """
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            await client._init_session()
            captcha = await client._solve_captcha()
            if not captcha:
                last_exc = CaptchaSolveError("OCR failed to read the CAPTCHA image.")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            form = {
                "cino": cnr,
                "appFlag": "web",
                "action_code": "fetchStateDistCourtNew",
                "caseStatusSearchType": "CNRNumber",
                "captcha": captcha,
            }
            try:
                resp = await client._http.post(
                    hc_endpoints.INDEX_QRY_URL,
                    data=form,
                    headers={"Referer": hc_endpoints.MAIN_PAGE_URL},
                )
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "HC Services CNR search attempt %d/%d failed: %s", attempt, MAX_RETRIES, exc
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue

            text = resp.text
            if "history_table" in text:
                return text
            if "there is an sql error" in text.lower():
                raise CaseNotFoundError(f"No case found for CNR {cnr!r} on the HC Services portal.")
            if "ERROR_VAL" in text or "invalid captcha" in text.lower():
                last_exc = CaptchaSolveError("HC Services portal rejected the CAPTCHA.")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)
                continue
            # Unrecognized response shape -- don't guess; surface it.
            last_exc = CourtPortalError(
                f"Unrecognized response from HC Services CNR search: {text[:300]!r}"
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

        if isinstance(last_exc, CaptchaSolveError):
            raise last_exc
        raise CourtPortalError(
            f"HC Services CNR search failed after {MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

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

    def _run_hierarchy_call(self, coro):
        """Run a captcha-free hierarchy-discovery coroutine (list_states/
        list_districts/list_complexes/list_benches/list_case_types),
        converting any bharat_courts/transport exception into the
        CourtDataError taxonomy the rest of this module and its callers
        (CourtStructureView, advocate_search's fan-out) already expect.

        Until this existed, these 5 methods had NO exception handling at
        all -- unlike every other portal-calling method in this file, a
        bharat_courts ServerError (the "Invalid Request" shape, or any
        other portal-side error message) or a raw transport failure
        propagated straight out as an unhandled exception. Confirmed by
        reading the code (not assumed) that the client wiring itself was
        already correct -- list_districts/list_complexes/list_court_options
        all already construct _TokenSeedingDistrictClient, same as
        search_by_advocate -- so this was never a "wrong client" bug; it
        was a missing try/except. Two concrete failure modes this fixes:
          - CourtStructureView.get() only catches CourtDataError/ValueError
            (see core/views/case_tracking.py); a raw DistrictServerError
            matched neither and surfaced as an unhandled 500 on
            GET /api/court-structure/.
          - advocate_search.run_advocate_search()'s very first call is
            provider.list_districts(state_code), deliberately unguarded
            there because a failure listing the state's districts leaves
            nothing to fan out over -- but it still deserves the same
            typed, _classify_failure-able error every per-district/
            per-complex failure downstream already gets, not a raw
            exception with no error_type.

        Deliberately a SINGLE attempt, not the MAX_RETRIES retry loop
        fetch_case/search_by_advocate use elsewhere in this file:
        advocate_search.py already retries list_complexes at the
        per-district level with its own backoff (see _search_district's
        caller), and CourtStructureView is a live form-load the user can
        just retry -- a second retry layer here would only add latency
        for both callers with no benefit.

        ValueError (an invalid hc_court_code -- a caller/client mistake,
        not a portal failure) and CourtDataError (nothing raises one from
        inside these coroutines today, but a future addition shouldn't be
        silently re-wrapped) pass through unchanged.
        """
        try:
            return asyncio.run(coro)
        except ValueError:
            raise
        except CourtDataError:
            raise
        except (DistrictCaptchaError, HCCaptchaError) as exc:
            raise CaptchaSolveError(
                f"The court portal's CAPTCHA rejected this request: {exc}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 -- any bharat_courts/transport failure
            raise CourtPortalError(f"The court portal could not be reached: {exc}") from exc

    def list_court_options(self, court_type: str) -> dict[str, str]:
        if court_type == "district":
            return self._cached(
                ("district_states",),
                lambda: self._run_hierarchy_call(self._list_district_states()),
            )
        if court_type == "high_court":
            return self._cached(
                ("hc_courts",),
                lambda: {c.code: c.name for c in list_all_courts() if c.court_type.value == "high_court"},
            )
        raise ValueError(f"Unknown court_type: {court_type!r}")

    async def _list_district_states(self) -> dict[str, str]:
        async with _TokenSeedingDistrictClient() as client:
            return await client.list_states()

    def list_districts(self, state_code: str) -> dict[str, str]:
        return self._cached(
            ("districts", state_code),
            lambda: self._run_hierarchy_call(self._list_districts(state_code)),
        )

    async def _list_districts(self, state_code: str) -> dict[str, str]:
        async with _TokenSeedingDistrictClient() as client:
            return await client.list_districts(state_code)

    def list_complexes(self, state_code: str, dist_code: str) -> dict[str, str]:
        return self._cached(
            ("complexes", state_code, dist_code),
            lambda: self._run_hierarchy_call(self._list_complexes(state_code, dist_code)),
        )

    async def _list_complexes(self, state_code: str, dist_code: str) -> dict[str, str]:
        async with _TokenSeedingDistrictClient() as client:
            return await client.list_complexes(state_code, dist_code)

    def list_benches(self, hc_court_code: str) -> dict[str, str]:
        return self._cached(
            ("benches", hc_court_code),
            lambda: self._run_hierarchy_call(self._list_benches(hc_court_code)),
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
            return self._cached(
                key, lambda: self._run_hierarchy_call(self._list_district_case_types(hierarchy))
            )
        if court_type == "high_court":
            key = ("hc_case_types", hierarchy["hc_court_code"], hierarchy.get("bench_code", "1"))
            return self._cached(
                key, lambda: self._run_hierarchy_call(self._list_hc_case_types(hierarchy))
            )
        raise ValueError(f"Unknown court_type: {court_type!r}")

    async def _list_district_case_types(self, hierarchy: dict) -> dict[str, str]:
        async with _TokenSeedingDistrictClient() as client:
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
