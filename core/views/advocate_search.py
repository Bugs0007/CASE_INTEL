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

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AdvocateSearchPreference, JobAlreadyRunningError, ProcessingJob

_BAR_CODE_RE = re.compile(r"^[A-Za-z]{2,3}/\d+/\d{4}$")
MAX_IMPORT_BATCH = 100

VALID_COURT_TYPES = ("district", "high_court")

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


class AdvocateSearchView(APIView):
    """Start an advocate search: state-wide (default, thorough) or scoped
    to one district (fast -- for an advocate who knows they mainly
    practice in one place).

    POST /api/cases/search-advocate/
    Body: {
        "name_or_bar_code": "<name, min 3 chars> or <STATE/NUMBER/YEAR>",
        "court_type": "district",     # "high_court" not supported yet
        "state_code": "<eCourts state code>",
        "dist_code": "<eCourts district code>",  # optional -- omit for
                                                   # the full state
        "status_filter": "Pending" | "Disposed" | "Both",  # optional
    }
    Enqueues a ProcessingJob (job_type="advocate_search") that fans the
    query out across every district/complex in the state (or just the one
    district, if dist_code was given), and returns {"job_id": ...}, 202.
    Poll AdvocateSearchStatusView for progress and results.
    """

    def post(self, request):
        court_type = request.data.get("court_type") or "district"
        if court_type != "district":
            return Response(
                {"detail": "Only District Courts advocate search is supported currently."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        state_code = request.data.get("state_code")
        if not state_code:
            return Response({"detail": "state_code is required."}, status=status.HTTP_400_BAD_REQUEST)

        dist_code = request.data.get("dist_code")

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
        if dist_code:
            job_params["districts_filter"] = [str(dist_code)]

        try:
            job = ProcessingJob.enqueue_advocate_search(request.user, job_params)
        except JobAlreadyRunningError as exc:
            return Response(
                {"detail": str(exc), "code": "search_already_running"},
                status=status.HTTP_409_CONFLICT,
            )

        AdvocateSearchPreference.objects.update_or_create(
            owner=request.user,
            defaults={"court_type": court_type, "hierarchy_config": {"state_code": str(state_code)}},
        )

        return Response({"job_id": job.id}, status=status.HTTP_202_ACCEPTED)


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
        results = all_results[:MAX_RESULTS_IN_RESPONSE]

        return Response(
            {
                "status": job.status,
                "cancel_requested": job.cancel_requested,
                "progress_current": job.progress_current,
                "progress_total": job.progress_total,
                "error": job.error,
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

        try:
            job = ProcessingJob.enqueue_advocate_search(
                request.user,
                {
                    "state_code": payload.get("state_code"),
                    "court_type": payload.get("court_type", "district"),
                    "advocate_name": payload.get("advocate_name", ""),
                    "bar_code": payload.get("bar_code", ""),
                    "status_filter": payload.get("status_filter", "Both"),
                    "districts_filter": failed_codes,
                    "seed_results": payload.get("results", []),
                    "seed_districts_status": seed_districts_status,
                    "retry_of": original.id,
                },
            )
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
            },
            status=status.HTTP_200_OK,
        )


class AdvocateSearchPreferenceView(APIView):
    """The caller's last-used state, for pre-filling the search page.

    GET /api/cases/search-advocate/preference/
    """

    def get(self, request):
        preference = AdvocateSearchPreference.objects.filter(owner=request.user).first()
        if preference is None:
            return Response(None, status=status.HTTP_200_OK)
        return Response(
            {
                "court_type": preference.court_type,
                "hierarchy_config": preference.hierarchy_config,
            },
            status=status.HTTP_200_OK,
        )
