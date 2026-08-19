"""
Advocate state-wide search: fan a single advocate-name / bar-code query
out across every district and court complex in a state (or a chosen
subset -- see districts_filter), then aggregate and dedupe the matches.

Runs ONLY inside the process_jobs worker (job_type="advocate_search") --
never inline in a request. A state can have 30-75 districts, each with
several court complexes, so this is dozens-to-hundreds of sequential
CAPTCHA-gated portal calls, far beyond a request timeout. (The manual
CNR-cascade setup in case_tracking.py still does its single-court lookup
inline; only this state-wide fan-out is async.)

Why fan out at all: the eCourts "Search by Advocate" form is scoped to ONE
court complex per query -- there is no state-wide advocate search on the
portal itself. An advocate with cases spread across a state would
otherwise have to search every court complex by hand. We trade a
long-running background job for actually finding every case.

Realistic runtime: ~3-5s per court complex (CAPTCHA solve + pacing, more
when CAPTCHA retries fire), plus one complex-list call per district. A
typical state (~25-35 districts, ~3 complexes each => ~100-150 searches)
lands around 10-15 minutes; a large state like Uttar Pradesh (~75
districts) can run 30-45 minutes.

Conservative toward the portal, same posture as court_order_sync.py /
advocate_import.py:
  - strictly sequential, SEARCH_DELAY_SECONDS apart, never parallel;
  - per-complex CAPTCHA/retry/backoff is inherited from
    EcourtsProvider.search_by_advocate (ADVOCATE_SEARCH_MAX_ATTEMPTS /
    RETRY_BACKOFF_SECONDS in ecourts_provider.py);
  - a COARSER district-level retry sits on top of that (see
    DISTRICT_RETRY_BACKOFF_SECONDS below) for the case where an entire
    district's complexes fail with the same "session" signature -- root-
    caused live 26 Jul 2026 on a run long enough to span dozens of minutes;
  - per-district AND per-complex failure isolation: one court complex
    failing its CAPTCHA, or a district's complex-list call failing, is
    recorded and skipped, never aborting the state-wide run;
  - dedup by cnr_number across every district/complex (the same case can
    surface under more than one complex).

Results and per-district status are persisted to job.payload
INCREMENTALLY, after every district (not only at the end) -- so the
frontend can show cases found so far while still running, and so a job
that dies mid-run (worker restart, OOM, etc.) leaves whatever was found
intact rather than losing the whole run. See districts_status in the
payload shape below; a separate "retry failed districts" job (enqueued via
AdvocateSearchRetryFailedView) re-runs only the districts that didn't
fully succeed, seeded with everything already collected.

Progress (job.progress_current/progress_total) is districts_done/total for
THIS run's district set (the full state, or a districts_filter subset for
a per-district search or a failed-districts retry) -- the only unit known
up front (a district's complex count isn't known until its list_complexes
call returns).
"""

from __future__ import annotations

import logging
import time

from core.models import ActivityLog, ProcessingJob
from core.services.court_data import CourtDataError, get_provider
from core.services.court_data.ecourts_parsing import parse_complex_code

logger = logging.getLogger(__name__)

# Inter-request pacing. Matches advocate_import.IMPORT_DELAY_SECONDS (both
# are status-page reads); intentionally lighter than court_order_sync's 5s,
# which is reserved for the more abuse-sensitive order-download endpoints.
SEARCH_DELAY_SECONDS = 1

# A whole-district retry is a coarser, more expensive fallback than the
# per-complex retries already inside EcourtsProvider.search_by_advocate --
# reserved for when a district looks systemically broken rather than one
# complex hitting a hard captcha run. Root-caused live 26 Jul 2026: on a
# run long enough to span dozens of minutes, some districts started failing
# EVERY complex with the same "Invalid Request" signature the app_token/
# delimeter fix (24 Jul) already targets -- even though
# _TokenSeedingDistrictClient re-seeds both fresh on every single attempt,
# so this isn't literally "stale local state" so much as it needing a
# genuinely later attempt (a real cooldown) to succeed, hence a much longer
# backoff here than the per-complex retry's ~1.5-9s.
DISTRICT_RETRY_BACKOFF_SECONDS = 20
MAX_DISTRICT_ATTEMPTS = 2


class AdvocateSearchCancelled(Exception):
    """Raised internally when a cancellation was requested mid-run (see
    ProcessingJob.request_cancel) -- caught by process_jobs.py, which
    finishes the job as "cancelled" instead of "succeeded". Everything
    persisted before the raise (results, districts_status) is kept."""


def _classify_failure(error_text: str) -> str:
    """Classify a district/complex failure for reporting + the district-
    level retry decision below.

    'session' -- the portal's own "Invalid Request" response, the same
        signature the app_token/delimeter root-cause fix (24 Jul 2026)
        targets. Worth a whole-district retry: this is not a wrong guess,
        it's the portal rejecting the request before captcha is even
        evaluated.
    'captcha' -- a plain wrong OCR guess ("Invalid Captcha"). Already
        retried per-attempt inside search_by_advocate; a district-level
        retry buys little extra here since each attempt already re-seeds a
        fresh session.
    'data' -- our own "returned an empty response" signal (missing/invalid
        dist_code or court_complex_code, see ecourts_provider.py). Retrying
        will not help; the code itself is bad.
    'portal' -- anything else (timeouts, connection errors, unrecognized
        response shapes).
    """
    lowered = error_text.lower()
    if "invalid request" in lowered:
        return "session"
    if "invalid captcha" in lowered or "captcha" in lowered:
        return "captcha"
    if "empty response" in lowered:
        return "data"
    return "portal"


def _search_district(
    provider, state_code: str, dist_code: str, dist_name: str,
    advocate_name: str, bar_code: str, status_filter: str,
) -> tuple[list, list[dict], int, int]:
    """Search every court complex in one district.

    Returns (cases, complex_failures, complexes_ok, complexes_total).
    Raises CourtDataError only if listing the district's own complexes
    fails (nothing to search this attempt) -- the caller decides whether
    to retry the whole district. Per-complex search failures are caught
    and isolated into complex_failures, same posture as before.
    """
    complexes = provider.list_complexes(state_code, dist_code)
    cases: list = []
    complex_failures: list[dict] = []
    complexes_ok = 0

    for complex_raw, complex_name in complexes.items():
        complex_code, est_code = parse_complex_code(complex_raw)
        time.sleep(SEARCH_DELAY_SECONDS)
        try:
            found = provider.search_by_advocate(
                {
                    "state_code": state_code,
                    "dist_code": dist_code,
                    "court_complex_code": complex_code,
                    "est_code": est_code,
                },
                advocate_name=advocate_name,
                bar_code=bar_code,
                status_filter=status_filter,
            )
        except CourtDataError as exc:
            error_text = str(exc)
            complex_failures.append({
                "district": dist_name,
                "court_complex": complex_name,
                "error": error_text,
                "error_type": _classify_failure(error_text),
            })
            continue
        except Exception as exc:  # noqa: BLE001 -- deliberate last-resort net
            # Defense in depth: EcourtsProvider.search_by_advocate already
            # wraps the network/transport failure this was written for
            # (httpx.RemoteProtocolError -- observed live 26 Jul 2026 when
            # a very common name made one complex's response body 25.7MB
            # and the connection was cut mid-body) into a retried
            # CourtPortalError, so this branch shouldn't normally fire. But
            # a run covering dozens of districts and hundreds of complexes
            # is exactly the kind of long, unattended job where an
            # anticipated-but-uncategorized failure must not be allowed to
            # take down everything already found -- one bad complex is
            # recorded and skipped, never a crashed job (see module
            # docstring's incremental-persistence rationale).
            error_text = f"{type(exc).__name__}: {exc}"
            logger.error(
                "Advocate search: UNEXPECTED exception in %s / %s -- isolating "
                "and continuing: %s",
                dist_name, complex_name, error_text, exc_info=True,
            )
            complex_failures.append({
                "district": dist_name,
                "court_complex": complex_name,
                "error": error_text,
                "error_type": "portal",
            })
            continue

        complexes_ok += 1
        cases.extend(found)

    return cases, complex_failures, complexes_ok, len(complexes)


def run_advocate_search(job: ProcessingJob, progress_callback=None) -> None:
    """Worker entry point for job_type="advocate_search".

    Reads search inputs from job.payload:
        {state_code, court_type, advocate_name, bar_code, status_filter,
         districts_filter?: list[str],       # restrict to these dist_codes
                                              # (per-district search, or a
                                              # failed-districts retry)
         seed_results?: list[dict],          # carried forward from a prior
                                              # run (retry-failed)
         seed_districts_status?: dict}       # ditto, districts already
                                              # known to have succeeded

    Writes the outcome back into the same payload, INCREMENTALLY after
    every district:
        {..inputs.., "results": [CaseInfo dicts], "failures": [...],
         "districts_total": int, "districts_done": int,
         "districts_status": {dist_code: {"name", "status": "success"|
             "failed"|"partial", "complexes_total", "complexes_ok",
             "complexes_failed"}},
         "complexes_searched": int}

    Never raises for per-district/per-complex portal failures -- those are
    isolated and recorded. Only a failure of the very first list_districts
    call (which leaves nothing to fan out over) propagates to the worker's
    own error handling and fails the job.
    """
    params = job.payload or {}
    state_code = params.get("state_code")
    advocate_name = params.get("advocate_name", "") or ""
    bar_code = params.get("bar_code", "") or ""
    status_filter = params.get("status_filter") or "Both"
    districts_filter = params.get("districts_filter")
    seed_results = params.get("seed_results") or []
    seed_districts_status = params.get("seed_districts_status") or {}

    provider = get_provider()

    # A failure HERE (listing the state's districts) is fatal to the whole
    # job -- there is nothing to fan out over -- so it deliberately
    # propagates to the worker and marks the job failed, unlike the
    # per-district failures below which are isolated.
    all_districts = provider.list_districts(state_code)
    if districts_filter:
        wanted = set(districts_filter)
        districts = {code: name for code, name in all_districts.items() if code in wanted}
    else:
        districts = all_districts
    total_districts = len(districts)

    results_by_cnr: dict[str, dict] = {
        r["cnr_number"]: r for r in seed_results if r.get("cnr_number")
    }
    failures: list[dict] = []
    districts_status: dict[str, dict] = dict(seed_districts_status)
    complexes_searched = 0

    def _persist() -> None:
        ProcessingJob.objects.filter(id=job.id).update(
            payload={
                **params,
                "results": list(results_by_cnr.values()),
                "failures": failures,
                "districts_total": total_districts,
                "districts_done": sum(
                    1 for code in districts if code in districts_status
                ),
                "districts_status": districts_status,
                "complexes_searched": complexes_searched,
            }
        )

    if progress_callback:
        progress_callback(0, total_districts)
    _persist()  # write immediately -- a job that dies before district 1 finishes still leaves a real row, not an empty one

    for i, (dist_code, dist_name) in enumerate(districts.items()):
        time.sleep(SEARCH_DELAY_SECONDS)

        cases: list = []
        complex_failures: list[dict] = []
        complexes_ok = 0
        complexes_total = 0
        list_error: Exception | None = None

        for attempt in range(1, MAX_DISTRICT_ATTEMPTS + 1):
            try:
                cases, complex_failures, complexes_ok, complexes_total = _search_district(
                    provider, state_code, dist_code, dist_name,
                    advocate_name, bar_code, status_filter,
                )
                list_error = None
            except CourtDataError as exc:
                list_error = exc
                logger.warning(
                    "Advocate search: complex-list failed for district %s (%s), "
                    "attempt %d/%d: %s",
                    dist_code, dist_name, attempt, MAX_DISTRICT_ATTEMPTS, exc,
                )
                if attempt < MAX_DISTRICT_ATTEMPTS:
                    time.sleep(DISTRICT_RETRY_BACKOFF_SECONDS)
                continue
            except Exception as exc:  # noqa: BLE001 -- last-resort net, see _search_district's comment
                list_error = exc
                logger.error(
                    "Advocate search: UNEXPECTED exception listing/searching district "
                    "%s (%s), attempt %d/%d -- isolating and continuing: %s",
                    dist_code, dist_name, attempt, MAX_DISTRICT_ATTEMPTS, exc, exc_info=True,
                )
                if attempt < MAX_DISTRICT_ATTEMPTS:
                    time.sleep(DISTRICT_RETRY_BACKOFF_SECONDS)
                continue

            # Every complex in this district failed with the "session"
            # signature -- treat as systemic (portal-side rejection, not a
            # per-complex wrong guess) and retry the WHOLE district
            # (re-listing complexes too) after a real cooldown, rather than
            # recording it as permanently failed on the first pass.
            session_failures = [f for f in complex_failures if f["error_type"] == "session"]
            looks_systemic = complexes_total > 0 and len(session_failures) >= complexes_total
            if looks_systemic and attempt < MAX_DISTRICT_ATTEMPTS:
                logger.warning(
                    "Advocate search: district %s (%s) failed all %d complexes "
                    "with session errors (attempt %d/%d) -- retrying the whole "
                    "district after a %ds cooldown.",
                    dist_code, dist_name, complexes_total, attempt,
                    MAX_DISTRICT_ATTEMPTS, DISTRICT_RETRY_BACKOFF_SECONDS,
                )
                time.sleep(DISTRICT_RETRY_BACKOFF_SECONDS)
                continue
            break

        if list_error is not None:
            complex_failures = [{
                "district": dist_name, "court_complex": None,
                "error": str(list_error), "error_type": _classify_failure(str(list_error)),
            }]
            complexes_ok = 0
            complexes_total = 0

        for case in cases:
            if case.cnr_number:  # dedup by CNR across every district/complex
                results_by_cnr[case.cnr_number] = case.to_dict()
        failures.extend(complex_failures)
        complexes_searched += complexes_ok

        if complexes_total == 0:
            dist_status = "failed"
        elif complexes_ok == complexes_total:
            dist_status = "success"
        elif complexes_ok == 0:
            dist_status = "failed"
        else:
            dist_status = "partial"

        districts_status[dist_code] = {
            "name": dist_name,
            "status": dist_status,
            "complexes_total": complexes_total,
            "complexes_ok": complexes_ok,
            "complexes_failed": complexes_total - complexes_ok,
        }

        # Persist BEFORE bumping progress -- these are two separate
        # ProcessingJob.objects.update() calls (progress via
        # progress_callback -> process_jobs.py's report_progress), and a
        # poll landing in between them must never see an advanced
        # progress_current with a still-stale payload. Persisting first
        # means the worst case is the opposite (payload slightly ahead of
        # the progress counter), which is harmless for the "show results
        # as they arrive" UX this exists for.
        _persist()
        if progress_callback:
            progress_callback(i + 1, total_districts)

        # Cancellation checkpoint -- the only point in the run where we
        # cheaply know results are fully persisted for everything done so
        # far. A running job can only be flagged (not finished) from the
        # cancel endpoint since the worker holds this row, so we poll for
        # that flag here, between districts, rather than mid-district
        # (interrupting a district's own captcha-retry loop isn't worth
        # the complexity for what's already the natural checkpoint
        # granularity this fan-out already persists at).
        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            ActivityLog.objects.create(
                owner=job.owner,
                case=None,
                activity_type="advocate_search",
                description=(
                    f"Advocate search cancelled after {i + 1} of {total_districts} "
                    f"district(s): {len(results_by_cnr)} case(s) found so far."
                ),
            )
            raise AdvocateSearchCancelled()

    results = list(results_by_cnr.values())
    succeeded = sum(1 for d in districts_status.values() if d["status"] == "success")
    ActivityLog.objects.create(
        owner=job.owner,
        case=None,
        activity_type="advocate_search",
        description=(
            f"Advocate search across {len(districts_status)} district(s) "
            f"({succeeded} fully succeeded): {len(results)} case(s) found"
            + (f", {len(failures)} court(s) skipped" if failures else "")
            + "."
        ),
    )
