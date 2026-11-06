"""
Advocate search views: search eCourts by advocate name / bar code across a
whole state (secondary entry point alongside the manual CNR entry in
case_tracking.py), and bulk-import selected results into new Cases.

Both search and import are ASYNC (ProcessingJob) here. The search fans a
single query out across every district and court complex in a state -- see
core/services/advocate_search.py for why that is dozens-to-hundreds of
sequential CAPTCHA-gated portal calls and must run in the worker, not a
request. The user only picks a STATE; the backend discovers the districts
and complexes itself.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    AdvocateSearchComplexRun,
    AdvocateSearchPreference,
    AdvocateSearchProfile,
    JobAlreadyRunningError,
    ProcessingJob,
)
from core.services.advocate_quick_search import quick_search_summary, remembered_complexes
from core.services.advocate_results import annotate_rows
from core.services.advocate_search_v2 import COURT_SITE_URL
from core.services.court_data import CourtDataError, get_provider
from core.services.high_court_registry import get_high_court
from core.services.name_matching import minimize_queries

_BAR_CODE_RE = re.compile(r"^[A-Za-z]{2,3}/\d+/\d{4}$")
MAX_IMPORT_BATCH = 100
# Benches in one High Court search: every bench is a full CAPTCHA-gated request.
MAX_HC_BENCHES = 8

VALID_COURT_TYPES = ("district", "high_court")

# A state has at most ~75 districts; this only stops an absurd request body.
MAX_DISTRICTS_PER_SEARCH = 100

# Hard cap on how many search results a single status response may carry.
#
# A state-wide search on a common advocate name legitimately matches tens of
# thousands of cases -- a real local job returned 130,032, which serialises to
# ~38.7 MB. The frontend polls this endpoint every 1.5s while a job runs, so
# an uncapped response meant repeatedly building a 38.7 MB string in a
# gunicorn worker on a 1 GB t3.micro with 2 workers: enough to exhaust memory
# and get the worker killed, which nginx surfaces as a 502 for whatever
# request happened to be in flight -- including an unrelated case-tracking
# refresh. It also froze the browser, which .map()s every row into the DOM.
#
# 500 is far more than anyone picks from by hand; past that the answer is to
# narrow the search, which results_total/results_truncated tell the user to do.
MAX_RESULTS_IN_RESPONSE = 500


def _parse_name_or_bar_code(raw: str) -> tuple[str, str, str | None]:
    """Return (advocate_name, bar_code, error). Exactly one of the first
    two is non-empty on success; error is a message when neither a valid
    name (>=3 chars) nor a STATE/NUMBER/YEAR bar code was given."""
    raw = (raw or "").strip()
    if _BAR_CODE_RE.match(raw):
        return "", raw, None
    if len(raw) >= 3:
        return raw, "", None
    return (
        "",
        "",
        "Enter an advocate name (at least 3 characters) or a bar code in "
        "STATE/NUMBER/YEAR format (e.g. MAH/1234/2015).",
    )


def _profile_for(request, payload: dict):
    """The caller's own search profile for a results read: `?profile_id=` wins
    over the one the job was started with. Owner-scoped, so another advocate's
    id (or a deleted one) reads as no profile."""
    raw = request.query_params.get("profile_id") or payload.get("profile_id")
    try:
        profile_id = int(raw)
    except (TypeError, ValueError):
        return None
    return AdvocateSearchProfile.objects.filter(pk=profile_id, owner=request.user).first()


def _parse_districts(dist_code, dist_codes) -> tuple[list[str], str | None]:
    """The districts a search is limited to, as (codes, error). `dist_codes`
    (a list) wins over the older single `dist_code`; neither means the whole
    state, returned as []."""
    if dist_codes is not None:
        if not isinstance(dist_codes, list) or any(
            not isinstance(code, (str, int)) or isinstance(code, bool) or not str(code).strip()
            for code in dist_codes
        ):
            return [], "dist_codes must be a list of district codes."
        codes = list(dict.fromkeys(str(code).strip() for code in dist_codes))
        if len(codes) > MAX_DISTRICTS_PER_SEARCH:
            return [], f"Pick at most {MAX_DISTRICTS_PER_SEARCH} districts."
        return codes, None
    if dist_code:
        return [str(dist_code)], None
    return [], None


class AdvocateSearchView(APIView):
    """Start an advocate search: state-wide (default, thorough), scoped to
    one or more districts (fast -- for an advocate who knows where they
    practice), or a Quick search of only the court complexes that returned
    cases for this advocate last time.

    POST /api/cases/search-advocate/
    Body: {
        "name_or_bar_code": "<name, min 3 chars> or <STATE/NUMBER/YEAR>",
        "court_type": "district",     # "high_court" not supported yet
        "state_code": "<eCourts state code>",
        "dist_codes": ["<district code>", ...],  # optional -- omit for
                                                   # the full state
        "dist_code": "<district code>",           # older single-district form
        "mode": "full" | "quick",     # optional, default "full"; "quick"
                                      # needs a remembered history (400
                                      # code "no_quick_history" without one)
        "status_filter": "Pending" | "Disposed" | "Both",  # optional
    }
    Enqueues a ProcessingJob (job_type="advocate_search") that fans the
    query out across every district/complex in the state (or just the chosen
    districts, or the remembered complexes), and returns {"job_id": ...}, 202.
    Poll AdvocateSearchStatusView for progress and results.
    """

    def post(self, request):
        # The redesigned search names a profile instead of a typed name; the old
        # request shape below is untouched and keeps working.
        if "profile_id" in request.data:
            return self._post_v2(request)

        court_type = request.data.get("court_type") or "district"
        if court_type != "district":
            return Response(
                {"detail": "Only District Courts advocate search is supported currently."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        state_code = request.data.get("state_code")
        if not state_code:
            return Response({"detail": "state_code is required."}, status=status.HTTP_400_BAD_REQUEST)

        districts, districts_error = _parse_districts(
            request.data.get("dist_code"), request.data.get("dist_codes")
        )
        if districts_error:
            return Response({"detail": districts_error}, status=status.HTTP_400_BAD_REQUEST)

        mode = request.data.get("mode") or "full"
        if mode not in ("full", "quick"):
            return Response({"detail": "mode must be 'full' or 'quick'."}, status=status.HTTP_400_BAD_REQUEST)

        status_filter = request.data.get("status_filter") or "Both"
        if status_filter not in ("Pending", "Disposed", "Both"):
            return Response(
                {"detail": "status_filter must be 'Pending', 'Disposed', or 'Both'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        advocate_name, bar_code, error = _parse_name_or_bar_code(request.data.get("name_or_bar_code"))
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        job_params = {
            "state_code": str(state_code),
            "court_type": court_type,
            "advocate_name": advocate_name,
            "bar_code": bar_code,
            "status_filter": status_filter,
        }
        if mode == "quick":
            remembered = remembered_complexes(request.user, advocate_name, bar_code, str(state_code))
            if not remembered:
                return Response(
                    {
                        "detail": "No courts are remembered for this advocate yet. Run a full search first.",
                        "code": "no_quick_history",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            job_params["complexes_filter"] = [
                {"dist_code": c["dist_code"], "complex_code": c["complex_code"], "est_code": c["est_code"]}
                for c in remembered
            ]
            job_params["mode"] = "quick"
        elif districts:
            job_params["districts_filter"] = districts
            job_params["mode"] = "districts"
        else:
            job_params["mode"] = "state"

        try:
            job = ProcessingJob.enqueue_advocate_search(request.user, job_params)
        except JobAlreadyRunningError as exc:
            return Response(
                {"detail": str(exc), "code": "search_already_running"},
                status=status.HTTP_409_CONFLICT,
            )

        # Remember the state and the chosen districts, and keep the Quick
        # search history that lives in the same row.
        existing = AdvocateSearchPreference.objects.filter(owner=request.user).first()
        config = dict(existing.hierarchy_config or {}) if existing else {}
        config["state_code"] = str(state_code)
        if mode != "quick":
            if districts:
                config["dist_codes"] = districts
            else:
                config.pop("dist_codes", None)
        AdvocateSearchPreference.objects.update_or_create(
            owner=request.user,
            defaults={"court_type": court_type, "hierarchy_config": config},
        )

        return Response({"job_id": job.id}, status=status.HTTP_202_ACCEPTED)

    def _post_v2(self, request):
        """POST /api/cases/search-advocate/ with {profile_id, state_code,
        dist_codes?, status_filter?, search_by?: "names"|"bar_code",
        bar_code?}. Needs ADVOCATE_SEARCH_V2. The queries come from the profile
        through the same minimisation the profile card shows, so what the
        advocate was told goes to eCourts is what goes."""
        if not settings.ADVOCATE_SEARCH_V2:
            return Response(
                {"detail": "The redesigned advocate search is not switched on.", "code": "v2_disabled"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            profile_id = int(request.data.get("profile_id"))
        except (TypeError, ValueError):
            profile_id = None
        profile = (
            AdvocateSearchProfile.objects.filter(pk=profile_id, owner=request.user).first() if profile_id else None
        )
        if profile is None:
            return Response({"detail": "Search profile not found."}, status=status.HTTP_400_BAD_REQUEST)

        court_type = request.data.get("court_type") or "district"
        if court_type not in ("district", "high_court"):
            return Response(
                {"detail": "court_type must be 'district' or 'high_court'."}, status=status.HTTP_400_BAD_REQUEST
            )
        high_court: dict | None = None
        districts: list[str] = []
        if court_type == "high_court":
            high_court, error_response = self._high_court_params(request)
            if error_response is not None:
                return error_response
            state_code = high_court["state_code"]
        else:
            state_code = request.data.get("state_code")
            if not state_code:
                return Response({"detail": "state_code is required."}, status=status.HTTP_400_BAD_REQUEST)
            districts, districts_error = _parse_districts(request.data.get("dist_code"), request.data.get("dist_codes"))
            if districts_error:
                return Response({"detail": districts_error}, status=status.HTTP_400_BAD_REQUEST)
        status_filter = request.data.get("status_filter") or "Both"
        if status_filter not in ("Pending", "Disposed", "Both"):
            return Response(
                {"detail": "status_filter must be 'Pending', 'Disposed', or 'Both'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        search_by = request.data.get("search_by") or ("bar_code" if profile.bar_codes else "names")
        if search_by not in ("names", "bar_code"):
            return Response({"detail": "search_by must be 'names' or 'bar_code'."}, status=status.HTTP_400_BAD_REQUEST)
        queries: list[str] = []
        bar_code = ""
        if search_by == "bar_code":
            wanted = str(request.data.get("bar_code") or (profile.bar_codes[0] if profile.bar_codes else "")).upper()
            if not wanted or wanted not in [c.upper() for c in profile.bar_codes]:
                return Response(
                    {"detail": "Add a bar enrolment number to the profile, or search by name."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            bar_code = wanted
        else:
            queries = minimize_queries(list(profile.name_forms or []))
            if not queries:
                return Response(
                    {"detail": "Add at least one name form of three or more letters to the profile."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        job_params = {
            "v2": True,
            "profile_id": profile.id,
            "search_by": search_by,
            "state_code": str(state_code),
            "court_type": court_type,
            "queries": queries,
            # What an import carries to guess the case's side: the shortest query.
            "advocate_name": queries[0] if queries else "",
            "bar_code": bar_code,
            "status_filter": status_filter,
            "mode": "high_court" if high_court else ("districts" if districts else "state"),
        }
        if districts:
            job_params["districts_filter"] = districts
        if high_court:
            job_params.update(high_court)
        try:
            job = ProcessingJob.enqueue_advocate_search(request.user, job_params)
        except JobAlreadyRunningError as exc:
            return Response(
                {"detail": str(exc), "code": "search_already_running"}, status=status.HTTP_409_CONFLICT
            )

        if high_court is None:  # the remembered state and districts are the District Courts tab's
            existing = AdvocateSearchPreference.objects.filter(owner=request.user).first()
            config = dict(existing.hierarchy_config or {}) if existing else {}
            config["state_code"] = str(state_code)
            if districts:
                config["dist_codes"] = districts
            else:
                config.pop("dist_codes", None)
            AdvocateSearchPreference.objects.update_or_create(
                owner=request.user, defaults={"court_type": court_type, "hierarchy_config": config}
            )
        body = {"job_id": job.id, "queries": queries, "portal_calls_per_court": max(1, len(queries))}
        if high_court and search_by == "names":
            body["warning"] = (
                "A High Court result row does not list the advocate, so rows from a name search cannot be "
                "told apart by name: every one needs checking. A bar number search is exact."
            )
        return Response(body, status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _high_court_params(request):
        """Validate the High Court part of a v2 start: the court, and benches that
        the portal itself lists for it. Returns (params, None) or (None, error
        response). The portal call (the bench list) is CAPTCHA-free and cached."""
        court = get_high_court(str(request.data.get("hc_court_code") or ""))
        if court is None:
            return None, Response(
                {"detail": "hc_court_code must be one of the courts at /api/cases/high-courts/."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not court["supported"]:
            return None, Response(
                {"detail": court["support_note"], "code": "high_court_unsupported"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        raw = request.data.get("bench_codes")
        if (
            not isinstance(raw, list)
            or not raw
            or any(not isinstance(c, (str, int)) or isinstance(c, bool) for c in raw)
        ):
            return None, Response({"detail": "Pick at least one bench."}, status=status.HTTP_400_BAD_REQUEST)
        codes = list(dict.fromkeys(str(c) for c in raw))
        if len(codes) > MAX_HC_BENCHES:
            return None, Response(
                {"detail": f"Pick at most {MAX_HC_BENCHES} benches: each one is a separate search."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            portal = get_provider().list_benches(court["code"])
        except CourtDataError as exc:
            return None, Response(
                {"detail": f"The court portal could not list this court's benches: {exc}", "code": "portal_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        unknown = [c for c in codes if c not in portal]
        if unknown:
            return None, Response(
                {"detail": f"Not a bench of this court: {', '.join(unknown)}."}, status=status.HTTP_400_BAD_REQUEST
            )
        return (
            {
                "hc_court_code": court["code"],
                "hc_court_name": court["name"],
                "state_code": court["state_code"],
                "bench_codes": codes,
                "bench_names": [portal[c] for c in codes],
            },
            None,
        )


class AdvocateSearchStatusView(APIView):
    """Poll the status/results of an advocate search job.

    GET /api/cases/search-advocate/<job_id>/

    `results` and `failures` are populated INCREMENTALLY as districts
    complete (not only once the whole job finishes), so polling mid-run
    already shows cases found so far -- see
    core/services/advocate_search.py's per-district _persist(). `status`
    is job.status ("queued"/"running"/"succeeded"/"failed"), never a 500
    for a partial/failed district (those show up in `failures` and
    `districts_status` instead) -- only a genuinely fatal failure (e.g.
    the state's district list itself couldn't be fetched) sets job.status
    to "failed".

    `districts_status` maps dist_code -> {name, status: "success"|
    "failed"|"partial", complexes_total/ok/failed} for every district
    attempted so far (including ones carried forward from a prior run via
    a failed-districts retry) -- the frontend uses this to show which
    districts are covered vs. still missing.
    """

    def get(self, request, job_id):
        try:
            job = ProcessingJob.objects.get(
                pk=job_id, owner=request.user, job_type="advocate_search"
            )
        except ProcessingJob.DoesNotExist:
            return Response({"detail": "Search job not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = job.payload or {}
        all_results = payload.get("results", [])

        # With a search profile (the redesigned search stores its id on the job,
        # or the caller names one), every row is labelled from the profile's
        # CURRENT name forms and Not me list, best match first, and the counts
        # cover all rows. Without one the rows are returned exactly as stored.
        profile = _profile_for(request, payload)
        all_results, match_counts = annotate_rows(all_results, profile)
        results = all_results[:MAX_RESULTS_IN_RESPONSE]

        return Response(
            {
                "status": job.status,
                "cancel_requested": job.cancel_requested,
                "progress_current": job.progress_current,
                "progress_total": job.progress_total,
                "error": job.error,
                "profile_id": profile.id if profile else None,
                "match_counts": match_counts,
                # What kind of search this was, so the page can reopen it on the
                # right tab after a refresh (the old searches simply read "district").
                "v2": bool(payload.get("v2")),
                "court_type": payload.get("court_type", "district"),
                "search_by": payload.get("search_by", ""),
                "queries": payload.get("queries", []),
                "state_code": payload.get("state_code", ""),
                "hc_court_name": payload.get("hc_court_name", ""),
                "results": results,
                # results_total is the real match count; results may be a
                # truncated prefix of it. See MAX_RESULTS_IN_RESPONSE for why
                # returning all of them took the API down.
                "results_total": len(all_results),
                "results_truncated": len(all_results) > len(results),
                "failures": payload.get("failures", []),
                "districts_total": payload.get("districts_total"),
                "districts_status": payload.get("districts_status", {}),
                "complexes_searched": payload.get("complexes_searched"),
                # Live counters: court complexes attempted so far, and how
                # many the districts listed so far hold (a district's count is
                # known once it is listed, so the total grows as the run goes).
                "complexes_done": payload.get("complexes_done"),
                "complexes_total_known": payload.get("complexes_total_known"),
                "current_district": payload.get("current_district", ""),
                "mode": payload.get("mode", "state"),
                "created_at": job.created_at,
                "started_at": job.started_at,
            },
            status=status.HTTP_200_OK,
        )


class AdvocateSearchActiveListView(APIView):
    """List the caller's own in-progress (queued/running) advocate
    searches, so a lost/refreshed page (or a 409 from the concurrency cap)
    can show what's actually running instead of a dead end.

    GET /api/cases/search-advocate/active/

    Owner-scoped, not system-wide -- the concurrency cap in
    ProcessingJob.enqueue_advocate_search is global across every user, but
    exposing another owner's search terms/results here would be the exact
    cross-tenant leak OwnerScopedMixin exists to prevent elsewhere. In
    practice this means a 409 caused by a DIFFERENT owner's job won't show
    up in this list -- only your own stuck/running searches do.
    """

    def get(self, request):
        jobs = ProcessingJob.active_of_type_for_owner("advocate_search", request.user)
        return Response(
            [
                {
                    "job_id": job.id,
                    "status": job.status,
                    "cancel_requested": job.cancel_requested,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "progress_current": job.progress_current,
                    "progress_total": job.progress_total,
                    "state_code": (job.payload or {}).get("state_code", ""),
                    "advocate_name": (job.payload or {}).get("advocate_name", ""),
                    "bar_code": (job.payload or {}).get("bar_code", ""),
                    "results_total": len((job.payload or {}).get("results", [])),
                }
                for job in jobs
            ],
            status=status.HTTP_200_OK,
        )


class AdvocateSearchCancelView(APIView):
    """Cancel one of the caller's own advocate search jobs.

    POST /api/cases/search-advocate/<job_id>/cancel/

    A queued job is cancelled immediately. A running job can't be stopped
    mid-district-batch -- the worker owns the row -- so this only flags
    it; run_advocate_search notices at its per-district checkpoint and
    finishes the job as "cancelled" itself (results found so far are kept,
    same as any other terminal state). Poll AdvocateSearchStatusView same
    as before to see it land.
    """

    def post(self, request, job_id):
        try:
            job = ProcessingJob.objects.get(
                pk=job_id, owner=request.user, job_type="advocate_search"
            )
        except ProcessingJob.DoesNotExist:
            return Response({"detail": "Search job not found."}, status=status.HTTP_404_NOT_FOUND)

        if job.status not in ("queued", "running"):
            return Response(
                {"detail": "This search has already finished; nothing to cancel."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job = job.request_cancel()
        return Response(
            {"status": job.status, "cancel_requested": job.cancel_requested},
            status=status.HTTP_200_OK,
        )


def _active_retry(user, job_id):
    """The queued/running child job retrying courts of this search, if any."""
    return ProcessingJob.objects.filter(
        job_type="advocate_search",
        owner=user,
        status__in=["queued", "running"],
        payload__parent_job_id=job_id,
    ).first()


def _seconds(run) -> int | None:
    if run.started_at and run.finished_at:
        return max(0, round((run.finished_at - run.started_at).total_seconds()))
    return None


def _run_dict(run) -> dict:
    Run = AdvocateSearchComplexRun
    if run.status == Run.FAILED:
        reason = run.last_error_message
        if run.attempts:
            reason += f" {run.attempts} attempt{'s' if run.attempts != 1 else ''}."
    elif run.status == Run.RUNNING:
        reason = "Searching"
    elif run.status == Run.PENDING:
        reason = "Waiting"
    else:
        reason = ""
    return {
        "id": run.id,
        "dist_code": run.dist_code,
        "dist_name": run.dist_name,
        "complex_name": run.complex_name,
        "status": run.status,
        "attempts": run.attempts,
        "error_code": run.last_error_code,
        "reason": reason,
        "raw_count": run.raw_count,
        "matched_count": run.matched_count,
        "seconds": _seconds(run),
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


class AdvocateSearchCourtsView(APIView):
    """Court-by-court status of an advocate search (the redesigned search).

    GET /api/cases/search-advocate/<job_id>/courts/

    `groups` lists every court complex under its district, with its status
    (pending / running / done / failed), the attempts spent, how many rows it
    returned and how many look like the advocate's, and for a failed one a
    plain-language `reason`. `needs_attention` is the failed courts, flat, for
    the pinned list; they can be searched again with POST .../retry/.
    `seconds_left` is the average time of the courts finished so far times the
    courts still to go (null until one has finished); an estimate, not a promise.
    """

    def get(self, request, job_id):
        job = ProcessingJob.objects.filter(pk=job_id, owner=request.user, job_type="advocate_search").first()
        if job is None:
            return Response({"detail": "Search job not found."}, status=status.HTTP_404_NOT_FOUND)
        Run = AdvocateSearchComplexRun
        runs = list(Run.objects.filter(job=job, owner=request.user).order_by("id"))
        retry = _active_retry(request.user, job.id)

        groups: dict[str, dict] = {}
        for run in runs:
            group = groups.setdefault(
                run.dist_code,
                {"dist_code": run.dist_code, "name": run.dist_name, "total": 0, "done": 0, "failed": 0, "running": 0, "runs": []},
            )
            group["total"] += 1
            if run.status == Run.DONE:
                group["done"] += 1
            elif run.status == Run.FAILED:
                group["failed"] += 1
            elif run.status == Run.RUNNING:
                group["running"] += 1
            group["runs"].append(_run_dict(run))

        finished = [_seconds(r) for r in runs if r.status in (Run.DONE, Run.FAILED)]
        finished = [s for s in finished if s is not None]
        unfinished = sum(1 for r in runs if r.status in (Run.PENDING, Run.RUNNING))
        seconds_left = round(sum(finished) / len(finished) * unfinished) if finished and unfinished else None
        is_terminal = job.status in ("succeeded", "partial", "failed", "cancelled")

        return Response(
            {
                "job": {
                    "id": job.id,
                    "status": job.status,
                    "cancel_requested": job.cancel_requested,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "is_retrying": retry is not None,
                    "retry_job_id": retry.id if retry else None,
                    "can_retry": bool(is_terminal and retry is None and (job.payload or {}).get("v2", False)),
                },
                "counts": {
                    "total": len(runs),
                    "done": sum(1 for r in runs if r.status == Run.DONE),
                    "failed": sum(1 for r in runs if r.status == Run.FAILED),
                    "running": sum(1 for r in runs if r.status == Run.RUNNING),
                    "pending": sum(1 for r in runs if r.status == Run.PENDING),
                    "raw": sum(r.raw_count for r in runs),
                    "matched": sum(r.matched_count for r in runs),
                },
                "seconds_left": seconds_left,
                "needs_attention": [_run_dict(r) for r in runs if r.status == Run.FAILED],
                "groups": list(groups.values()),
                "court_site_url": COURT_SITE_URL,
            },
            status=status.HTTP_200_OK,
        )


class AdvocateSearchRetryView(APIView):
    """Search again only some courts of a finished search, merging into it.

    POST /api/cases/search-advocate/<job_id>/retry/
    Body: {"only_failed": true}  or  {"complex_ids": [<court run id>, ...]}

    Creates a child job for just those courts (the one-search-at-a-time cap
    still applies: 409 if any search is running) and sends their rows back to
    `pending`. The child's results are merged into THIS job's results and court
    list, so the advocate keeps one list: poll .../courts/ and the status
    endpoint of THIS job. Returns {"job_id": <child>, "parent_job_id", "courts"}, 202.
    """

    MAX_COMPLEX_IDS = 500

    def post(self, request, job_id):
        if not settings.ADVOCATE_SEARCH_V2:
            return Response(
                {"detail": "The redesigned advocate search is not switched on.", "code": "v2_disabled"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        job = ProcessingJob.objects.filter(pk=job_id, owner=request.user, job_type="advocate_search").first()
        if job is None:
            return Response({"detail": "Search job not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = job.payload or {}
        if not payload.get("v2") or payload.get("parent_job_id"):
            return Response(
                {"detail": "Only a search started from the redesigned page can be retried court by court."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if job.status not in ("succeeded", "partial", "failed", "cancelled"):
            return Response({"detail": "The search is still running."}, status=status.HTTP_400_BAD_REQUEST)
        if _active_retry(request.user, job.id) is not None:
            return Response(
                {"detail": "These courts are already being searched again.", "code": "retry_in_progress"},
                status=status.HTTP_409_CONFLICT,
            )

        Run = AdvocateSearchComplexRun
        only_failed = request.data.get("only_failed")
        ids = request.data.get("complex_ids")
        if (only_failed is True) == (ids is not None):
            return Response(
                {"detail": "Send either only_failed: true or complex_ids: [...]."}, status=status.HTTP_400_BAD_REQUEST
            )
        runs_qs = Run.objects.filter(job=job, owner=request.user)
        if only_failed is True:
            runs = list(runs_qs.filter(status=Run.FAILED).order_by("id"))
        else:
            if (
                not isinstance(ids, list)
                or len(ids) > self.MAX_COMPLEX_IDS
                or any(not isinstance(i, int) or isinstance(i, bool) for i in ids)
            ):
                return Response(
                    {"detail": "complex_ids must be a list of court ids."}, status=status.HTTP_400_BAD_REQUEST
                )
            runs = list(runs_qs.filter(id__in=ids).exclude(status=Run.RUNNING).order_by("id"))
        if not runs:
            return Response({"detail": "Nothing to search again."}, status=status.HTTP_400_BAD_REQUEST)

        child_params = {
            "v2": True,
            "parent_job_id": job.id,
            "run_ids": [r.id for r in runs],
            "state_code": payload.get("state_code"),
            "court_type": payload.get("court_type", "district"),
            "status_filter": payload.get("status_filter", "Both"),
            "queries": payload.get("queries", []),
            "bar_code": payload.get("bar_code", ""),
            "profile_id": payload.get("profile_id"),
            "search_by": payload.get("search_by"),
            "advocate_name": payload.get("advocate_name", ""),
        }
        try:
            # One transaction: the worker must never claim the child before the
            # courts are back to "pending".
            with transaction.atomic():
                child = ProcessingJob.enqueue_advocate_search(request.user, child_params)
                for run in runs:
                    if run.status != Run.PENDING:
                        run.reset_for_retry()
        except JobAlreadyRunningError as exc:
            return Response(
                {"detail": str(exc), "code": "search_already_running"}, status=status.HTTP_409_CONFLICT
            )
        return Response(
            {"job_id": child.id, "parent_job_id": job.id, "courts": len(runs)}, status=status.HTTP_202_ACCEPTED
        )


class AdvocateSearchRetryFailedView(APIView):
    """Re-run ONLY the districts that didn't fully succeed in a previous
    search job, reusing its already-collected results rather than
    re-searching the whole state.

    POST /api/cases/search-advocate/<job_id>/retry-failed/
    Enqueues a NEW ProcessingJob (job_type="advocate_search"), seeded with
    the original job's results and its successfully-searched districts'
    status, with districts_filter set to just the failed/partial ones.
    Returns {"job_id": ...}, 202 -- poll it exactly like a fresh search;
    its districts_status carries forward the original successes too, so
    it reads as a continuation, not a restart.
    """

    def post(self, request, job_id):
        try:
            original = ProcessingJob.objects.get(
                pk=job_id, owner=request.user, job_type="advocate_search"
            )
        except ProcessingJob.DoesNotExist:
            return Response({"detail": "Search job not found."}, status=status.HTTP_404_NOT_FOUND)

        if original.status not in ("succeeded", "failed"):
            return Response(
                {"detail": "The original search is still running."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = original.payload or {}
        districts_status = payload.get("districts_status", {})
        failed_codes = [code for code, d in districts_status.items() if d.get("status") != "success"]
        if not failed_codes:
            return Response(
                {"detail": "Nothing to retry -- every district already succeeded."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        seed_districts_status = {
            code: d for code, d in districts_status.items() if d.get("status") == "success"
        }

        retry_params = {
            "state_code": payload.get("state_code"),
            "court_type": payload.get("court_type", "district"),
            "advocate_name": payload.get("advocate_name", ""),
            "bar_code": payload.get("bar_code", ""),
            "status_filter": payload.get("status_filter", "Both"),
            "districts_filter": failed_codes,
            "seed_results": payload.get("results", []),
            "seed_districts_status": seed_districts_status,
            "retry_of": original.id,
            "mode": payload.get("mode", "state"),
        }
        # A Quick search retries only its remembered complexes in the
        # districts that fell short, never the whole district.
        if payload.get("complexes_filter"):
            retry_params["complexes_filter"] = [
                c for c in payload["complexes_filter"] if str(c.get("dist_code")) in failed_codes
            ]

        try:
            job = ProcessingJob.enqueue_advocate_search(request.user, retry_params)
        except JobAlreadyRunningError as exc:
            return Response(
                {"detail": str(exc), "code": "search_already_running"},
                status=status.HTTP_409_CONFLICT,
            )

        return Response({"job_id": job.id}, status=status.HTTP_202_ACCEPTED)


class AdvocateSearchImportView(APIView):
    """Bulk-import selected advocate-search results into new Cases.

    POST /api/cases/search-advocate/import/
    Body: {"court_type": "district", "selected": [{"cnr_number": ...,
           "case_number": ..., "petitioner": ..., "respondent": ...,
           "court_name": ...}, ...], "search_job_id": <optional>}
    Enqueues an async ProcessingJob (job_type="advocate_import") -- each
    selected case is fetched sequentially, 1s apart (req: rate-limit,
    eCourts is CAPTCHA-gated). Returns {"job_id": ...}, 202.

    search_job_id, when given, identifies the advocate_search job these
    results came from -- its payload already holds the advocate_name/
    bar_code the caller searched with (see AdvocateSearchView), which gets
    carried into the import job so run_advocate_import can auto-detect
    each new Case's user_party_role. Missing/not-found/not-owned just means
    no auto-detection is attempted for this batch (safe no-op, not an
    error) -- there's nothing else that depends on it.
    """

    def post(self, request):
        selected = request.data.get("selected")
        if not isinstance(selected, list) or not selected:
            return Response({"detail": "selected must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)
        if len(selected) > MAX_IMPORT_BATCH:
            return Response(
                {"detail": f"At most {MAX_IMPORT_BATCH} cases can be added in one batch."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate court_type here, the way AdvocateSearchView already does.
        # Without this, an arbitrary value ("banana", "High Court", "") was
        # written straight through to Case.court_type and
        # tracking_config["court_type"] -- Django does not enforce `choices`
        # on save() -- producing cases that could never refresh: every later
        # fetch raised ValueError("Unknown court_type") out of the provider.
        court_type = request.data.get("court_type") or "district"
        if court_type not in VALID_COURT_TYPES:
            return Response(
                {"detail": f"court_type must be one of: {', '.join(VALID_COURT_TYPES)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized = []
        for item in selected:
            if not isinstance(item, dict):
                continue
            item_court_type = item.get("court_type") or court_type
            if item_court_type not in VALID_COURT_TYPES:
                return Response(
                    {
                        "detail": (
                            f"Invalid court_type {item_court_type!r} on a selected "
                            f"case. Must be one of: {', '.join(VALID_COURT_TYPES)}."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            normalized.append({**item, "court_type": item_court_type})

        advocate_name = ""
        bar_code = ""
        search_job_id = request.data.get("search_job_id")
        if search_job_id:
            search_job = ProcessingJob.objects.filter(
                pk=search_job_id, owner=request.user, job_type="advocate_search"
            ).first()
            if search_job is not None:
                search_payload = search_job.payload or {}
                advocate_name = search_payload.get("advocate_name", "") or ""
                bar_code = search_payload.get("bar_code", "") or ""

        try:
            job = ProcessingJob.enqueue_advocate_import(
                request.user, normalized, advocate_name=advocate_name, bar_code=bar_code
            )
        except JobAlreadyRunningError as exc:
            return Response(
                {"detail": str(exc), "code": "import_already_running"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response({"job_id": job.id}, status=status.HTTP_202_ACCEPTED)


class AdvocateSearchImportStatusView(APIView):
    """Poll the status/result of a bulk-import job.

    GET /api/cases/search-advocate/import/<job_id>/
    """

    def get(self, request, job_id):
        try:
            job = ProcessingJob.objects.get(
                pk=job_id, owner=request.user, job_type="advocate_import"
            )
        except ProcessingJob.DoesNotExist:
            return Response({"detail": "Import job not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = job.payload or {}
        return Response(
            {
                "status": job.status,
                "progress_current": job.progress_current,
                "progress_total": job.progress_total,
                "error": job.error,
                "created": payload.get("created", []),
                "skipped_duplicate": payload.get("skipped_duplicate", []),
                "skipped_conflict": payload.get("skipped_conflict", []),
                "failed": payload.get("failed", []),
                # {cnr: [conflict hit, ...]} -- possible conflicts of
                # interest, flagged but never blocking (conflict_check.py).
                "conflicts": payload.get("conflicts", {}),
            },
            status=status.HTTP_200_OK,
        )


class AdvocateSearchPreferenceView(APIView):
    """The caller's last-used state and districts, for pre-filling the search
    page, and whether a Quick search is available.

    GET /api/cases/search-advocate/preference/
    GET /api/cases/search-advocate/preference/?name_or_bar_code=...&state_code=...

    With the query, `quick_search` is {complexes, districts, updated_at} when
    this advocate has remembered courts in that state, else null.
    """

    def get(self, request):
        preference = AdvocateSearchPreference.objects.filter(owner=request.user).first()
        if preference is None:
            return Response(None, status=status.HTTP_200_OK)
        config = {k: v for k, v in (preference.hierarchy_config or {}).items() if k != "quick"}

        quick = None
        advocate_name, bar_code, error = _parse_name_or_bar_code(request.query_params.get("name_or_bar_code"))
        state_code = request.query_params.get("state_code") or config.get("state_code")
        if not error and state_code:
            quick = quick_search_summary(request.user, advocate_name, bar_code, str(state_code))
        return Response(
            {
                "court_type": preference.court_type,
                "hierarchy_config": config,
                "quick_search": quick,
            },
            status=status.HTTP_200_OK,
        )
