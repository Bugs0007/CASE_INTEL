"""
Advocate state-wide search: fan a single advocate-name / bar-code query
out across EVERY district and court complex in a state, then aggregate and
dedupe the matches.

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
districts) can run 30-45 minutes. This is exactly why it is async.

Conservative toward the portal, same posture as court_order_sync.py /
advocate_import.py:
  - strictly sequential, SEARCH_DELAY_SECONDS apart, never parallel;
  - CAPTCHA/retry/backoff is inherited per call from
    EcourtsProvider.search_by_advocate (MAX_RETRIES / RETRY_BACKOFF_SECONDS
    in ecourts_provider.py) -- not re-implemented here;
  - per-district AND per-complex failure isolation: one court complex
    failing its CAPTCHA, or a district's complex-list call failing, is
    recorded and skipped, never aborting the state-wide run;
  - dedup by cnr_number across every district/complex (the same case can
    surface under more than one complex).

Progress is reported as districts_done / total_districts -- the only unit
known up front (a district's complex count isn't known until its
list_complexes call returns), and a meaningful "12 of 34 districts" bar.
"""

from __future__ import annotations

import logging
import time

from core.models import ActivityLog, ProcessingJob
from core.services.court_data import CourtDataError, get_provider
from core.services.court_data.ecourts_provider import parse_complex_code

logger = logging.getLogger(__name__)

# Inter-request pacing. Matches advocate_import.IMPORT_DELAY_SECONDS (both
# are status-page reads); intentionally lighter than court_order_sync's 5s,
# which is reserved for the more abuse-sensitive order-download endpoints.
SEARCH_DELAY_SECONDS = 1


def run_advocate_search(job: ProcessingJob, progress_callback=None) -> None:
    """Worker entry point for job_type="advocate_search".

    Reads the search inputs from job.payload ({state_code, court_type,
    advocate_name, bar_code, status_filter}) and writes the outcome back
    into the same payload:
        {..inputs.., "results": [CaseInfo dicts], "failures": [...],
         "districts_total": int, "districts_done": int,
         "complexes_searched": int}

    Never raises for per-district/per-complex portal failures -- those are
    isolated and recorded. Only a genuinely unexpected bug, or a failure of
    the very first list_districts call (which leaves nothing to fan out
    over), propagates to the worker's own error handling and fails the job.
    """
    params = job.payload or {}
    state_code = params.get("state_code")
    advocate_name = params.get("advocate_name", "") or ""
    bar_code = params.get("bar_code", "") or ""
    status_filter = params.get("status_filter") or "Both"

    provider = get_provider()

    # A failure HERE (listing the state's districts) is fatal to the whole
    # job -- there is nothing to fan out over -- so it deliberately
    # propagates to the worker and marks the job failed, unlike the
    # per-district failures below which are isolated.
    districts = provider.list_districts(state_code)
    total_districts = len(districts)

    results_by_cnr: dict[str, dict] = {}
    failures: list[dict] = []
    complexes_searched = 0

    if progress_callback:
        progress_callback(0, total_districts)

    for i, (dist_code, dist_name) in enumerate(districts.items()):
        time.sleep(SEARCH_DELAY_SECONDS)
        try:
            complexes = provider.list_complexes(state_code, dist_code)
        except CourtDataError as exc:
            logger.warning(
                "Advocate search: complex-list failed for district %s (%s): %s",
                dist_code, dist_name, exc,
            )
            failures.append({"district": dist_name, "court_complex": None, "error": str(exc)})
            if progress_callback:
                progress_callback(i + 1, total_districts)
            continue

        for complex_raw, complex_name in complexes.items():
            complex_code, est_code = parse_complex_code(complex_raw)
            time.sleep(SEARCH_DELAY_SECONDS)
            try:
                cases = provider.search_by_advocate(
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
                logger.warning(
                    "Advocate search: search failed in %s / %s: %s",
                    dist_name, complex_name, exc,
                )
                failures.append(
                    {"district": dist_name, "court_complex": complex_name, "error": str(exc)}
                )
                continue

            complexes_searched += 1
            for case in cases:
                if case.cnr_number:  # dedup by CNR across every district/complex
                    results_by_cnr[case.cnr_number] = case.to_dict()

        if progress_callback:
            progress_callback(i + 1, total_districts)

    results = list(results_by_cnr.values())
    ProcessingJob.objects.filter(id=job.id).update(
        payload={
            **params,
            "results": results,
            "failures": failures,
            "districts_total": total_districts,
            "districts_done": total_districts,
            "complexes_searched": complexes_searched,
        }
    )

    ActivityLog.objects.create(
        owner=job.owner,
        case=None,
        activity_type="advocate_search",
        description=(
            f"Advocate search across {total_districts} district(s): "
            f"{len(results)} case(s) found"
            + (f", {len(failures)} court(s) skipped" if failures else "")
            + "."
        ),
    )
