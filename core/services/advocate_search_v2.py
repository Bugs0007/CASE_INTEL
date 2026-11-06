"""The redesigned advocate search, as the worker runs it (job payload `v2: true`).

What differs from core/services/advocate_search.py, which still runs every old
request unchanged:

  * The unit of work shown to the advocate is the COURT COMPLEX. Each one has an
    AdvocateSearchComplexRun row, written as it starts and again as it ends, so
    the status screen lists every court live and "Found so far" fills as courts
    finish. A court that fails stays `failed` with a plain-language reason; it is
    never retried silently, only when the advocate asks (see `run_retry`).
  * The search is by the profile's minimised name queries (one portal request per
    query per court) or by bar code. Every raw row comes back (`keep_all`) with the
    advocate cell as listed; which rows are the advocate's own is decided when the
    results are read (core/services/advocate_results.py), so Not me / That's me
    never need a new search.
  * A retry is a CHILD job that searches only the chosen courts and merges what it
    finds into the PARENT job's results and runs, so the advocate keeps looking at
    one list.

Conservative toward eCourts, exactly as before: strictly sequential (one portal
request at a time, SEARCH_DELAY_SECONDS apart, never parallel), the provider's
bounded per-court attempts with backoff, a bounded whole-district retry for the
"Invalid Request" signature, and a court whose first query fails is not tried
with its second query (a failing portal is not hammered). No CAPTCHA-solving
service; the automatic reader is the provider's own.

Nothing here logs an advocate's name, a bar code or a CAPTCHA: log lines carry
job, district and court CODES and error kinds only.
"""

from __future__ import annotations

import contextlib
import logging
import time

import httpx
from django.conf import settings
from django.db import transaction

from core.models import ActivityLog, AdvocateSearchComplexRun, AdvocateSearchProfile, ProcessingJob
from core.services.advocate_results import BAR_CODE_SOURCE, count_visible
from core.services.advocate_search import (
    DISTRICT_RETRY_BACKOFF_SECONDS,
    MAX_DISTRICT_ATTEMPTS,
    SEARCH_DELAY_SECONDS,
    AdvocateSearchCancelled,
    _classify_failure,
    _Timings,
)
from core.services.court_data import CaptchaSolveError, CourtDataError, get_provider
from core.services.court_data.ecourts_parsing import parse_complex_code

logger = logging.getLogger(__name__)

Run = AdvocateSearchComplexRun

# The one portal front page a failed court links to: the District Courts site
# cannot be deep-linked to a court complex, so the advocate picks it there.
COURT_SITE_URL = "https://services.ecourts.gov.in/ecourtindia_v6/"

ERROR_MESSAGES = {
    Run.PORTAL_DISCONNECT: "Portal disconnected.",
    Run.CAPTCHA_FAILED: "Captcha not solved.",
    Run.TIMEOUT: "The court site did not answer in time.",
    Run.PARSE_ERROR: "The court site's answer could not be read.",
    Run.PORTAL_ERROR: "The court site refused the request.",
}


def classify_run_error(exc: BaseException) -> str:
    """One of the Run error codes for whatever ended a court's search. Reads the
    exception and its causes (the provider wraps the transport error it gave up
    on in a CourtPortalError), never the advocate's data."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and len(chain) < 6 and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(e, CaptchaSolveError) for e in chain):
        return Run.CAPTCHA_FAILED
    if any(isinstance(e, httpx.TimeoutException) for e in chain):
        return Run.TIMEOUT
    if any(isinstance(e, httpx.TransportError) for e in chain):
        return Run.PORTAL_DISCONNECT
    text = " ".join(str(e).lower() for e in chain)
    if "captcha" in text:
        return Run.CAPTCHA_FAILED
    if "timed out" in text or "did not answer within" in text or "timeout" in text:
        return Run.TIMEOUT
    if any(word in text for word in ("peer closed", "disconnected", "connection reset", "remote protocol", "connection error")):
        return Run.PORTAL_DISCONNECT
    if not isinstance(exc, CourtDataError):
        return Run.PARSE_ERROR  # our own code choked on what the portal sent
    return Run.PORTAL_ERROR


class _ComplexResult:
    def __init__(self) -> None:
        self.hits: list = []
        self.attempts = 0
        self.error: BaseException | None = None


def _attempts(searcher) -> int:
    timing = getattr(searcher, "last_search_timing", None)
    return int(timing.get("attempts") or 0) if isinstance(timing, dict) else 0


def _search_complex(searcher, hierarchy: dict, *, queries: list[str], bar_code: str, status_filter: str) -> _ComplexResult:
    """Every query on one court complex, one portal request at a time. Rows are
    deduplicated by CNR across queries. The first query that fails ends this
    court's search (rows already read are kept)."""
    result = _ComplexResult()
    seen: set[str] = set()
    for index, query in enumerate(queries or [None]):
        if index:
            time.sleep(SEARCH_DELAY_SECONDS)
        try:
            if "hc_court_code" in hierarchy:  # a High Court bench, not a district court complex
                found = searcher.search_hc_by_advocate(
                    hierarchy["hc_court_code"],
                    hierarchy["bench_code"],
                    advocate_name=query or "",
                    bar_code="" if query else bar_code,
                    status_filter=status_filter,
                    bench_name=hierarchy.get("bench_name", ""),
                )
            else:
                found = searcher.search_by_advocate(
                    hierarchy,
                    advocate_name=query or "",
                    bar_code="" if query else bar_code,
                    status_filter=status_filter,
                    keep_all=True,
                )
        except Exception as exc:  # noqa: BLE001 -- one bad court must never end the run
            result.attempts += _attempts(searcher)
            result.error = exc
            break
        result.attempts += _attempts(searcher)
        for hit in found:
            key = hit.cnr_number
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            result.hits.append(hit)
    return result


def _hierarchy(run: AdvocateSearchComplexRun, ctx: dict) -> dict:
    """What the provider needs to find this court: a district court complex, or a
    High Court bench (its portal bench code is stored as the run's complex_code)."""
    if ctx["court_type"] == "high_court":
        return {"hc_court_code": ctx["hc_court_code"], "bench_code": run.complex_code, "bench_name": run.complex_name}
    return {
        "state_code": ctx["state_code"],
        "dist_code": run.dist_code,
        "court_complex_code": run.complex_code,
        "est_code": run.est_code,
    }


def _row(hit, run: AdvocateSearchComplexRun, *, bar_mode: bool) -> dict:
    row = hit.to_dict()
    row.update(
        dist_code=run.dist_code,
        dist_name=run.dist_name,
        complex_code=run.complex_code,
        est_code=run.est_code,
        complex_name=run.complex_name,
    )
    if bar_mode:
        row["match_source"] = BAR_CODE_SOURCE
    return row


def _profile(owner, profile_id):
    if not profile_id:
        return None
    return AdvocateSearchProfile.objects.filter(pk=profile_id, owner=owner).first()


# ---------------------------------------------------------------------------
# What the job payload (and so the old status fields) says, read from the runs
# ---------------------------------------------------------------------------


def summarize_runs(job: ProcessingJob) -> dict:
    """The payload fields the status endpoint has always carried, derived from
    the job's court-complex rows: districts_status, the live counters and the
    failures list. Derived rather than kept by hand, so a retry that finishes a
    court corrects every number at once."""
    runs = list(Run.objects.filter(job=job))
    districts: dict[str, dict] = {}
    for run in runs:
        d = districts.setdefault(
            run.dist_code,
            {"name": run.dist_name, "complexes_total": 0, "complexes_ok": 0, "complexes_failed": 0, "unfinished": 0},
        )
        d["complexes_total"] += 1
        if run.status == Run.DONE:
            d["complexes_ok"] += 1
        elif run.status == Run.FAILED:
            d["complexes_failed"] += 1
        else:
            d["unfinished"] += 1
    districts_status: dict[str, dict] = {}
    for code, d in districts.items():
        if d["unfinished"]:
            continue  # only districts whose courts have all finished carry a verdict
        status = "success" if d["complexes_failed"] == 0 else ("failed" if d["complexes_ok"] == 0 else "partial")
        districts_status[code] = {
            "name": d["name"],
            "status": status,
            "complexes_total": d["complexes_total"],
            "complexes_ok": d["complexes_ok"],
            "complexes_failed": d["complexes_failed"],
        }
    failures = [
        {
            "district": run.dist_name,
            "court_complex": run.complex_name or None,
            "error": run.last_error_message,
            "error_type": run.last_error_code,
        }
        for run in runs
        if run.status == Run.FAILED
    ]
    return {
        "districts_status": districts_status,
        "failures": failures,
        "complexes_searched": sum(1 for r in runs if r.status == Run.DONE),
        "complexes_done": sum(1 for r in runs if r.status in (Run.DONE, Run.FAILED)),
        "complexes_total_known": len(runs),
    }


# ---------------------------------------------------------------------------
# One court complex: the single place a Run moves pending -> running -> done|failed
# ---------------------------------------------------------------------------


def _run_court(searcher, run: AdvocateSearchComplexRun, ctx: dict, timings: _Timings | None) -> list[dict]:
    """Search one court and record the outcome on its row. Returns the rows it
    found (also when it failed part-way)."""
    time.sleep(SEARCH_DELAY_SECONDS)
    run.mark_running()
    started = time.perf_counter()
    result = _search_complex(
        searcher,
        _hierarchy(run, ctx),
        queries=ctx["queries"],
        bar_code=ctx["bar_code"],
        status_filter=ctx["status_filter"],
    )
    elapsed = time.perf_counter() - started
    rows = [_row(hit, run, bar_mode=ctx["bar_mode"]) for hit in result.hits if hit.cnr_number]
    visible = count_visible(rows, ctx["profile"])
    code = ""
    if result.error is None:
        run.mark_done(attempts=result.attempts, raw_count=len(result.hits), matched_count=visible)
    else:
        code = classify_run_error(result.error)
        logger.warning(
            "Advocate search v2: job=%s dist=%s complex=%s failed (%s) after %d attempt(s).",
            ctx["job_id"], run.dist_code, run.complex_code, code, result.attempts,
        )
        run.mark_failed(
            attempts=result.attempts,
            error_code=code,
            error_message=ERROR_MESSAGES[code],
            raw_count=len(result.hits),
            matched_count=visible,
        )
    if timings is not None:
        timings.record(
            run.dist_code, run.complex_code, getattr(searcher, "last_search_timing", None), elapsed,
            _classify_failure(str(result.error)) if result.error is not None else "",
        )
    return rows


@contextlib.contextmanager
def _searcher(provider, court_type: str = "district"):
    """One portal session for a district's courts when session reuse is on. A High
    Court bench always has a session of its own (the reusable one is the District
    Courts portal's)."""
    reuse = (
        court_type != "high_court"
        and bool(getattr(settings, "ADVOCATE_SEARCH_REUSE_SESSION", False))
        and hasattr(provider, "advocate_search_session")
    )
    with (provider.advocate_search_session() if reuse else contextlib.nullcontext(provider)) as searcher:
        yield searcher


def _context(job: ProcessingJob, params: dict) -> dict:
    queries = [q for q in (params.get("queries") or []) if q]
    bar_code = params.get("bar_code", "") or ""
    return {
        "job_id": job.id,
        "court_type": params.get("court_type") or "district",
        "hc_court_code": params.get("hc_court_code") or "",
        "hc_court_name": params.get("hc_court_name") or "",
        # {portal bench code: bench name}, in the order chosen
        "benches": dict(zip(params.get("bench_codes") or [], params.get("bench_names") or [])),
        "state_code": str(params.get("state_code")),
        "queries": queries,
        "bar_code": bar_code,
        "bar_mode": bool(bar_code) and not queries,
        "status_filter": params.get("status_filter") or "Both",
        "profile": _profile(job.owner, params.get("profile_id")),
        "query_label": " | ".join(queries) if queries else bar_code,
    }


def _ensure_runs(job: ProcessingJob, dist_code: str, dist_name: str, complexes: dict, ctx: dict) -> list[AdvocateSearchComplexRun]:
    runs = []
    for complex_raw, complex_name in complexes.items():
        if ctx["court_type"] == "high_court":
            complex_code, est_code = str(complex_raw), ""
        else:
            complex_code, est_code = parse_complex_code(complex_raw)
        run, _ = Run.objects.get_or_create(
            job=job,
            owner=job.owner,
            dist_code=str(dist_code),
            complex_code=str(complex_code),
            est_code=str(est_code or ""),
            defaults={"dist_name": dist_name, "complex_name": complex_name, "query": ctx["query_label"]},
        )
        runs.append(run)
    return runs


def _district_listing_failed(job: ProcessingJob, dist_code: str, dist_name: str, exc: BaseException, ctx: dict) -> None:
    """The district's courts could not even be listed: one failed row stands for
    all of them, and a retry re-lists the district."""
    code = classify_run_error(exc)
    run, _ = Run.objects.get_or_create(
        job=job,
        owner=job.owner,
        dist_code=str(dist_code),
        complex_code="",
        est_code="",
        defaults={"dist_name": dist_name, "complex_name": f"All courts in {dist_name}", "query": ctx["query_label"]},
    )
    if run.status == Run.FAILED:
        run.reset_for_retry()
    if run.status == Run.PENDING:
        run.mark_running()
    run.mark_failed(attempts=MAX_DISTRICT_ATTEMPTS, error_code=code, error_message=ERROR_MESSAGES[code])


# ---------------------------------------------------------------------------
# The worker entry points
# ---------------------------------------------------------------------------


def run_advocate_search_v2(job: ProcessingJob, progress_callback=None) -> None:
    """Worker entry for an advocate_search job whose payload says `v2`.

    A job with `parent_job_id` is a RETRY of some courts of an earlier search;
    anything else is a fresh search of the chosen districts.
    """
    params = job.payload or {}
    if params.get("parent_job_id"):
        return run_retry(job, progress_callback)

    ctx = _context(job, params)
    districts_filter = params.get("districts_filter")
    provider = get_provider()
    timings = _Timings(job.id)

    # A reclaimed job (crashed worker) starts over, so nothing half-written from
    # the dead attempt is left looking like a live court.
    Run.objects.filter(job=job).delete()

    # Listing the state's districts is fatal when it fails (nothing to fan out
    # over); the provider already retried a dropped connection with backoff.
    if ctx["court_type"] == "high_court":
        # One "district": the High Court itself; its courts are the chosen benches.
        districts = {ctx["hc_court_code"]: ctx["hc_court_name"]}
    else:
        all_districts = provider.list_districts(ctx["state_code"])
        wanted = set(districts_filter or ())
        districts = {c: n for c, n in all_districts.items() if c in wanted} if wanted else all_districts

    results_by_cnr: dict[str, dict] = {}
    live = {"district": ""}
    timing_summary: dict | None = None

    def persist() -> None:
        payload = {
            **params,
            "results": list(results_by_cnr.values()),
            "districts_total": len(districts),
            "districts_done": 0,
            "current_district": live["district"],
            **summarize_runs(job),
        }
        payload["districts_done"] = len(payload["districts_status"])
        if timing_summary is not None:
            payload["timing"] = timing_summary
        ProcessingJob.objects.filter(id=job.id).update(payload=payload)

    if progress_callback:
        progress_callback(0, len(districts))
    persist()

    for i, (dist_code, dist_name) in enumerate(districts.items()):
        time.sleep(SEARCH_DELAY_SECONDS)
        live["district"] = dist_name

        for attempt in range(1, MAX_DISTRICT_ATTEMPTS + 1):
            try:
                if ctx["court_type"] == "high_court":
                    complexes = ctx["benches"]
                else:
                    complexes = provider.list_complexes(ctx["state_code"], dist_code)
            except Exception as exc:  # noqa: BLE001 -- one district must not end the run
                logger.warning(
                    "Advocate search v2: courts of district %s could not be listed (attempt %d/%d).",
                    dist_code, attempt, MAX_DISTRICT_ATTEMPTS,
                )
                if attempt < MAX_DISTRICT_ATTEMPTS:
                    time.sleep(DISTRICT_RETRY_BACKOFF_SECONDS)
                    continue
                _district_listing_failed(job, dist_code, dist_name, exc, ctx)
                break

            runs = _ensure_runs(job, dist_code, dist_name, complexes, ctx)
            persist()
            with _searcher(provider, ctx["court_type"]) as searcher:
                for run in runs:
                    if run.status != Run.PENDING:
                        continue
                    for row in _run_court(searcher, run, ctx, timings):
                        results_by_cnr[row["cnr_number"]] = row
                    persist()
                    job.refresh_from_db(fields=["cancel_requested"])
                    if job.cancel_requested:
                        _finish_cancelled(job, timings, len(results_by_cnr), i + 1, len(districts))
                        timing_summary = timings.summary()
                        persist()
                        raise AdvocateSearchCancelled()

            # Every court failed the portal's "Invalid Request": systemic, so wait
            # and read the whole district again once (bounded), as the old search does.
            failed = [r for r in runs if r.status == Run.FAILED]
            looks_systemic = (
                bool(runs) and len(failed) == len(runs) and all(r.last_error_code == Run.PORTAL_ERROR for r in failed)
            )
            if looks_systemic and attempt < MAX_DISTRICT_ATTEMPTS:
                logger.warning(
                    "Advocate search v2: every court of district %s was refused (attempt %d/%d); "
                    "waiting %ds before reading it again.",
                    dist_code, attempt, MAX_DISTRICT_ATTEMPTS, DISTRICT_RETRY_BACKOFF_SECONDS,
                )
                time.sleep(DISTRICT_RETRY_BACKOFF_SECONDS)
                for run in failed:
                    run.reset_for_retry()
                continue
            break

        persist()
        if progress_callback:
            progress_callback(i + 1, len(districts))

    timing_summary = timings.summary()
    persist()
    summary = summarize_runs(job)
    ActivityLog.objects.create(
        owner=job.owner,
        case=None,
        activity_type="advocate_search",
        description=(
            f"Advocate search across {len(districts)} district(s): {len(results_by_cnr)} row(s) found, "
            f"{len(summary['failures'])} court(s) failed. " + timings.describe()
        ),
    )


def _finish_cancelled(job: ProcessingJob, timings: _Timings, found: int, done: int, total: int) -> None:
    ActivityLog.objects.create(
        owner=job.owner,
        case=None,
        activity_type="advocate_search",
        description=(
            f"Advocate search cancelled after {done} of {total} district(s): {found} row(s) found so far. "
            + timings.describe()
        ),
    )


def run_retry(job: ProcessingJob, progress_callback=None) -> None:
    """Search again only the courts named in this child job's `run_ids`, and fold
    what they return into the parent's results and runs.

    The courts' rows were sent back to `pending` when the retry was requested
    (see AdvocateSearchRetryView). A row standing for a district whose courts
    could not be listed (empty complex_code) re-lists the district and is replaced
    by one row per court.
    """
    params = job.payload or {}
    parent = ProcessingJob.objects.get(pk=params["parent_job_id"], owner=job.owner, job_type="advocate_search")
    ctx = _context(job, {**(parent.payload or {}), **{k: v for k, v in params.items() if v not in (None, "")}})
    ctx["job_id"] = parent.id
    provider = get_provider()
    timings = _Timings(job.id)

    wanted = Run.objects.filter(job=parent, owner=job.owner, id__in=params.get("run_ids") or [], status=Run.PENDING)
    pending = list(wanted.order_by("id"))
    total = len(pending)
    if progress_callback:
        progress_callback(0, total)

    done = 0
    for run in pending:
        if run.complex_code == "":
            courts = _expand_district(parent, run, provider, ctx)
        else:
            courts = [run]
        with _searcher(provider, ctx["court_type"]) as searcher:
            for court in courts:
                if court.status != Run.PENDING:
                    continue
                rows = _run_court(searcher, court, ctx, timings)
                _merge_into_parent(parent.id, rows)
        done += 1
        if progress_callback:
            progress_callback(done, total)
        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            raise AdvocateSearchCancelled()

    ActivityLog.objects.create(
        owner=job.owner,
        case=None,
        activity_type="advocate_search",
        description=f"Advocate search retry: {total} court(s) searched again. " + timings.describe(),
    )


def _expand_district(parent: ProcessingJob, run: AdvocateSearchComplexRun, provider, ctx: dict) -> list[AdvocateSearchComplexRun]:
    """Re-list a district whose courts could not be read: replace its one failed
    row by a row per court. If listing fails again the row fails again."""
    try:
        complexes = provider.list_complexes(ctx["state_code"], run.dist_code)
    except Exception as exc:  # noqa: BLE001
        code = classify_run_error(exc)
        run.mark_running()
        run.mark_failed(attempts=1, error_code=code, error_message=ERROR_MESSAGES[code])
        _merge_into_parent(parent.id, [])
        return []
    dist_code, dist_name = run.dist_code, run.dist_name
    run.delete()
    return _ensure_runs(parent, dist_code, dist_name, complexes, ctx)


def _merge_into_parent(parent_id: int, rows: list[dict]) -> None:
    """Add a retried court's rows to the parent's results (a row seen again is
    replaced by its newer copy) and refresh the parent's counters from its runs."""
    with transaction.atomic():
        parent = ProcessingJob.objects.select_for_update().get(pk=parent_id)
        payload = dict(parent.payload or {})
        by_cnr = {r["cnr_number"]: r for r in payload.get("results", []) if r.get("cnr_number")}
        for row in rows:
            by_cnr[row["cnr_number"]] = row
        payload["results"] = list(by_cnr.values())
        payload.update(summarize_runs(parent))
        payload["districts_done"] = len(payload["districts_status"])
        ProcessingJob.objects.filter(pk=parent_id).update(payload=payload)
