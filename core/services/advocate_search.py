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
call returns). Finer-grained counters ride in the payload as complexes
are searched (complexes_done / complexes_total_known), and the results
found so far are written after every complex, not only every district.

Timing: every complex logs one INFO line (district and complex CODES, never a
name, and no CAPTCHA text) with the seconds spent in session start, court
selection, CAPTCHA fetch+OCR and submit, its attempts and its outcome; the run
ends with a summary in payload["timing"] and in the ActivityLog entry. See
_Timings.

Quick search: a search that finishes records which court complexes returned
cases for this advocate (advocate_quick_search.py); a later search can pass
`complexes_filter` to visit only those.
"""

from __future__ import annotations

import contextlib
import logging
import time

from django.conf import settings

from core.models import ActivityLog, ProcessingJob
from core.services.advocate_quick_search import remember_search
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


class _Timings:
    """What one search spent its time on -- numbers only, never a name or a
    CAPTCHA reading. Fed one court complex at a time from the provider's
    `last_search_timing`; read once at the end for the payload and the
    ActivityLog line, and one INFO log line per complex as it goes."""

    def __init__(self, job_id: int) -> None:
        self.job_id = job_id
        self.started = time.monotonic()
        self.steps = {"init_s": 0.0, "setup_s": 0.0, "captcha_s": 0.0, "submit_s": 0.0, "retry_wait_s": 0.0}
        self.attempts: dict[str, int] = {"1": 0, "2": 0, "3+": 0}
        self.failure_classes: dict[str, int] = {}
        self.ok = 0
        self.failed = 0

    def record(self, dist_code: str, complex_code: str, timing, elapsed: float, failure_class: str) -> None:
        """`timing` is the provider's per-step seconds for the complex (None
        for a provider that does not report any); `elapsed` is the wall time
        of the whole call, so what the steps do not explain was spent waiting
        between attempts."""
        timing = timing if isinstance(timing, dict) else {}
        steps = {key: float(timing.get(key) or 0.0) for key in ("init_s", "setup_s", "captcha_s", "submit_s")}
        wait = max(0.0, elapsed - sum(steps.values()))
        attempts = int(timing.get("attempts") or 0)
        for key, value in steps.items():
            self.steps[key] += value
        self.steps["retry_wait_s"] += wait
        if attempts:
            self.attempts["1" if attempts == 1 else "2" if attempts == 2 else "3+"] += 1
        if failure_class:
            self.failed += 1
            self.failure_classes[failure_class] = self.failure_classes.get(failure_class, 0) + 1
        else:
            self.ok += 1
        logger.info(
            "Advocate search timing job=%s dist=%s complex=%s init=%.2fs setup=%.2fs captcha=%.2fs "
            "submit=%.2fs wait=%.2fs total=%.2fs attempts=%d outcome=%s",
            self.job_id, dist_code, complex_code, steps["init_s"], steps["setup_s"], steps["captcha_s"],
            steps["submit_s"], wait, elapsed, attempts, failure_class or "ok",
        )

    def summary(self) -> dict:
        total = time.monotonic() - self.started
        searched = self.ok + self.failed
        return {
            "total_seconds": round(total, 1),
            "complexes_searched": searched,
            "complexes_ok": self.ok,
            "complexes_failed": self.failed,
            "avg_seconds_per_complex": round(total / searched, 2) if searched else None,
            "step_seconds": {key: round(value, 1) for key, value in self.steps.items()},
            "attempt_histogram": dict(self.attempts),
            "failure_classes": dict(self.failure_classes),
            "reuse_session": bool(getattr(settings, "ADVOCATE_SEARCH_REUSE_SESSION", False)),
        }

    def describe(self) -> str:
        """One sentence for the ActivityLog line."""
        summary = self.summary()
        searched = summary["complexes_searched"]
        if not searched:
            return f"Timing: {summary['total_seconds']:.0f}s, no court complex searched."
        steps = summary["step_seconds"]
        per = lambda key: steps[key] / searched  # noqa: E731 -- tiny local formatter
        histogram = summary["attempt_histogram"]
        text = (
            f"Timing: {summary['total_seconds']:.0f}s in total, {searched} court complex(es) "
            f"({summary['avg_seconds_per_complex']:.1f}s each). Per complex: session start "
            f"{per('init_s'):.1f}s, court select {per('setup_s'):.1f}s, CAPTCHA fetch+OCR "
            f"{per('captcha_s'):.1f}s, submit {per('submit_s'):.1f}s, retry waits {per('retry_wait_s'):.1f}s. "
            f"Attempts: 1x {histogram['1']}, 2x {histogram['2']}, 3+ {histogram['3+']}."
        )
        if summary["failure_classes"]:
            text += " Failures: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["failure_classes"].items())) + "."
        if summary["reuse_session"]:
            text += " Session reuse is on."
        return text


def _search_district(
    provider, state_code: str, dist_code: str, dist_name: str,
    advocate_name: str, bar_code: str, status_filter: str,
    *, timings: _Timings | None = None, on_listed=None, on_complex=None,
    only_complexes: set[tuple[str, str]] | None = None,
) -> tuple[list, list[dict], int, int]:
    """Search every court complex in one district (or, for a Quick search,
    only `only_complexes`: a set of (complex_code, est_code)).

    Returns (cases, complex_failures, complexes_ok, complexes_total).
    Raises CourtDataError only if listing the district's own complexes
    fails (nothing to search this attempt) -- the caller decides whether
    to retry the whole district. Per-complex search failures are caught
    and isolated into complex_failures, same posture as before.

    `on_listed(total)` fires once the district's complexes are known and
    `on_complex(outcome_dict)` after each complex, so the caller can keep
    its progress and results current while the district is still running.
    With ADVOCATE_SEARCH_REUSE_SESSION on, the district's complexes share
    one portal session (see EcourtsProvider.advocate_search_session).
    """
    complexes = provider.list_complexes(state_code, dist_code)
    if only_complexes is not None:
        complexes = {
            raw: name for raw, name in complexes.items() if _complex_ident(*parse_complex_code(raw)) in only_complexes
        }
    cases: list = []
    complex_failures: list[dict] = []
    complexes_ok = 0
    if on_listed:
        on_listed(len(complexes))

    reuse = bool(getattr(settings, "ADVOCATE_SEARCH_REUSE_SESSION", False)) and hasattr(
        provider, "advocate_search_session"
    )
    with (provider.advocate_search_session() if reuse else contextlib.nullcontext(provider)) as searcher:
        for index, (complex_raw, complex_name) in enumerate(complexes.items(), start=1):
            complex_code, est_code = parse_complex_code(complex_raw)
            time.sleep(SEARCH_DELAY_SECONDS)
            failure: dict | None = None
            found: list = []
            started = time.perf_counter()
            try:
                found = searcher.search_by_advocate(
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
                failure = {
                    "district": dist_name,
                    "court_complex": complex_name,
                    "error": error_text,
                    "error_type": _classify_failure(error_text),
                }
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
                    "Advocate search: UNEXPECTED exception in %s / %s -- isolating and "
                    "continuing: %s",
                    dist_name, complex_name, error_text, exc_info=True,
                )
                failure = {
                    "district": dist_name,
                    "court_complex": complex_name,
                    "error": error_text,
                    "error_type": "portal",
                }
            elapsed = time.perf_counter() - started

            if timings is not None:
                timings.record(
                    dist_code, complex_code, getattr(searcher, "last_search_timing", None), elapsed,
                    failure["error_type"] if failure else "",
                )
            if failure is not None:
                complex_failures.append(failure)
            else:
                complexes_ok += 1
                cases.extend(found)
            if on_complex:
                on_complex({
                    "index": index,
                    "total": len(complexes),
                    "dist_code": dist_code,
                    "dist_name": dist_name,
                    "complex_code": complex_code,
                    "est_code": est_code,
                    "complex_name": complex_name,
                    "cases": None if failure is not None else found,
                })

    return cases, complex_failures, complexes_ok, len(complexes)


def _complex_ident(complex_code, est_code) -> tuple[str, str]:
    return (str(complex_code), str(est_code or ""))


def _complex_filter(params: dict) -> dict[str, set[tuple[str, str]]] | None:
    """{dist_code: {(complex_code, est_code), ...}} for a Quick search, from
    the payload's `complexes_filter`; None for a search over whole districts."""
    entries = params.get("complexes_filter")
    if not entries:
        return None
    wanted: dict[str, set[tuple[str, str]]] = {}
    for entry in entries:
        wanted.setdefault(str(entry["dist_code"]), set()).add(
            _complex_ident(entry["complex_code"], entry.get("est_code"))
        )
    return wanted


def run_advocate_search(job: ProcessingJob, progress_callback=None) -> None:
    """Worker entry point for job_type="advocate_search".

    Reads search inputs from job.payload:
        {state_code, court_type, advocate_name, bar_code, status_filter,
         districts_filter?: list[str],       # restrict to these dist_codes
                                              # (one or several districts, or
                                              # a failed-districts retry)
         complexes_filter?: list[{dist_code, complex_code, est_code}],
                                              # Quick search: only these court
                                              # complexes (implies their
                                              # districts)
         seed_results?: list[dict],          # carried forward from a prior
                                              # run (retry-failed)
         seed_districts_status?: dict}       # ditto, districts already
                                              # known to have succeeded

    Writes the outcome back into the same payload, INCREMENTALLY after
    every court complex (the counters and results) and every district (its
    status):
        {..inputs.., "results": [CaseInfo dicts], "failures": [...],
         "districts_total": int, "districts_done": int,
         "districts_status": {dist_code: {"name", "status": "success"|
             "failed"|"partial", "complexes_total", "complexes_ok",
             "complexes_failed"}},
         "complexes_searched": int,          # read successfully so far
         "complexes_done": int,              # attempted so far, ok or not
         "complexes_total_known": int,       # complexes in the districts listed so far
         "current_district": str,
         "timing": {...}}                    # once the run ends, see _Timings.summary

    Never raises for per-district/per-complex portal failures -- those are
    isolated and recorded. Only a failure of the very first list_districts
    call (which leaves nothing to fan out over) propagates to the worker's
    own error handling and fails the job.
    """
    params = job.payload or {}
    if params.get("v2"):
        # The redesigned search (profiles, per-court status, retry): its own
        # runner, so everything below stays exactly as the old requests ran it.
        from core.services.advocate_search_v2 import run_advocate_search_v2

        return run_advocate_search_v2(job, progress_callback)
    state_code = params.get("state_code")
    advocate_name = params.get("advocate_name", "") or ""
    bar_code = params.get("bar_code", "") or ""
    status_filter = params.get("status_filter") or "Both"
    districts_filter = params.get("districts_filter")
    complexes_filter = _complex_filter(params)
    seed_results = params.get("seed_results") or []
    seed_districts_status = params.get("seed_districts_status") or {}

    provider = get_provider()
    timings = _Timings(job.id)

    # A failure HERE (listing the state's districts) is fatal to the whole
    # job -- there is nothing to fan out over -- so it deliberately
    # propagates to the worker and marks the job failed, unlike the
    # per-district failures below which are isolated.
    all_districts = provider.list_districts(state_code)
    wanted = set(districts_filter or ())
    if complexes_filter is not None:
        wanted |= set(complexes_filter)
    if wanted:
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
    # Live counters for the court complexes of the district in progress,
    # on top of those of the districts already finished.
    done_before = 0
    live = {"done": 0, "total": 0, "ok": 0, "district": ""}
    searched_ok: list[dict] = []  # every complex read successfully, for Quick search
    timing_summary: dict | None = None

    def _persist() -> None:
        payload = {
            **params,
            "results": list(results_by_cnr.values()),
            "failures": failures,
            "districts_total": total_districts,
            "districts_done": sum(
                1 for code in districts if code in districts_status
            ),
            "districts_status": districts_status,
            "complexes_searched": complexes_searched + live["ok"],
            "complexes_done": done_before + live["done"],
            "complexes_total_known": done_before + live["total"],
            "current_district": live["district"],
        }
        if timing_summary is not None:
            payload["timing"] = timing_summary
        ProcessingJob.objects.filter(id=job.id).update(payload=payload)

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
        district_ok: list[dict] = []
        live.update(done=0, total=0, ok=0, district=dist_name)

        def _on_listed(total: int) -> None:
            live["total"] = total
            _persist()

        def _on_complex(outcome: dict) -> None:
            live["done"] = outcome["index"]
            live["total"] = outcome["total"]
            found = outcome["cases"]
            if found is not None:
                live["ok"] += 1
                district_ok.append({
                    "dist_code": outcome["dist_code"], "dist_name": outcome["dist_name"],
                    "complex_code": outcome["complex_code"], "est_code": outcome["est_code"],
                    "complex_name": outcome["complex_name"], "cases": len(found),
                })
                for case in found:
                    if case.cnr_number:  # same CNR dedup as the district merge below
                        results_by_cnr[case.cnr_number] = case.to_dict()
            _persist()

        for attempt in range(1, MAX_DISTRICT_ATTEMPTS + 1):
            live.update(done=0, total=0, ok=0)
            district_ok.clear()
            try:
                cases, complex_failures, complexes_ok, complexes_total = _search_district(
                    provider, state_code, dist_code, dist_name,
                    advocate_name, bar_code, status_filter,
                    timings=timings, on_listed=_on_listed, on_complex=_on_complex,
                    only_complexes=(complexes_filter or {}).get(dist_code) if complexes_filter else None,
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
            district_ok.clear()

        for case in cases:
            if case.cnr_number:  # dedup by CNR across every district/complex
                results_by_cnr[case.cnr_number] = case.to_dict()
        failures.extend(complex_failures)
        complexes_searched += complexes_ok
        searched_ok.extend(district_ok)
        done_before += complexes_total
        live.update(done=0, total=0, ok=0)

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
            timing_summary = timings.summary()
            _persist()
            ActivityLog.objects.create(
                owner=job.owner,
                case=None,
                activity_type="advocate_search",
                description=(
                    f"Advocate search cancelled after {i + 1} of {total_districts} "
                    f"district(s): {len(results_by_cnr)} case(s) found so far. "
                    + timings.describe()
                ),
            )
            raise AdvocateSearchCancelled()

    results = list(results_by_cnr.values())
    succeeded = sum(1 for d in districts_status.values() if d["status"] == "success")
    timing_summary = timings.summary()
    _persist()
    ActivityLog.objects.create(
        owner=job.owner,
        case=None,
        activity_type="advocate_search",
        description=(
            f"Advocate search across {len(districts_status)} district(s) "
            f"({succeeded} fully succeeded): {len(results)} case(s) found"
            + (f", {len(failures)} court(s) skipped" if failures else "")
            + ". "
            + timings.describe()
        ),
    )
    remember_search(
        job.owner, advocate_name=advocate_name, bar_code=bar_code,
        state_code=str(state_code), searched_ok=searched_ok,
    )
