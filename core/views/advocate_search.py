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
    """Start a state-wide advocate search.

    POST /api/cases/search-advocate/
    Body: {
        "name_or_bar_code": "<name, min 3 chars> or <STATE/NUMBER/YEAR>",
        "court_type": "district",     # "high_court" not supported yet
        "state_code": "<eCourts state code>",
        "status_filter": "Pending" | "Disposed" | "Both",  # optional
    }
    Enqueues a ProcessingJob (job_type="advocate_search") that fans the
    query out across every district/complex in the state, and returns
    {"job_id": ...}, 202. Poll AdvocateSearchStatusView for progress and
    results.
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

        status_filter = request.data.get("status_filter") or "Both"
        if status_filter not in ("Pending", "Disposed", "Both"):
            return Response(
                {"detail": "status_filter must be 'Pending', 'Disposed', or 'Both'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        advocate_name, bar_code, error = _parse_name_or_bar_code(request.data.get("name_or_bar_code"))
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            job = ProcessingJob.enqueue_advocate_search(
                request.user,
                {
                    "state_code": str(state_code),
                    "court_type": court_type,
                    "advocate_name": advocate_name,
                    "bar_code": bar_code,
                    "status_filter": status_filter,
                },
            )
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
    """Poll the status/results of a state-wide advocate search job.

    GET /api/cases/search-advocate/<job_id>/

    While running, `results` is empty and progress_current/progress_total
    are districts_done/total_districts. On success, `results` holds the
    deduped matches and `failures` lists any court complexes skipped
    (CAPTCHA/portal errors) -- a partial result is still a valid, useful
    outcome, not an error. A failed job (e.g. the state's district list
    couldn't be fetched at all) surfaces via status="failed" + error,
    never a 500 here.
    """

    def get(self, request, job_id):
        try:
            job = ProcessingJob.objects.get(
                pk=job_id, owner=request.user, job_type="advocate_search"
            )
        except ProcessingJob.DoesNotExist:
            return Response({"detail": "Search job not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = job.payload or {}
        return Response(
            {
                "status": job.status,
                "progress_current": job.progress_current,
                "progress_total": job.progress_total,
                "error": job.error,
                "results": payload.get("results", []),
                "failures": payload.get("failures", []),
                "districts_total": payload.get("districts_total"),
                "complexes_searched": payload.get("complexes_searched"),
            },
            status=status.HTTP_200_OK,
        )


class AdvocateSearchImportView(APIView):
    """Bulk-import selected advocate-search results into new Cases.

    POST /api/cases/search-advocate/import/
    Body: {"court_type": "district", "selected": [{"cnr_number": ...,
           "case_number": ..., "petitioner": ..., "respondent": ...,
           "court_name": ...}, ...]}
    Enqueues an async ProcessingJob (job_type="advocate_import") -- each
    selected case is fetched sequentially, 1s apart (req: rate-limit,
    eCourts is CAPTCHA-gated). Returns {"job_id": ...}, 202.
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

        court_type = request.data.get("court_type") or "district"
        normalized = [
            {**item, "court_type": item.get("court_type") or court_type}
            for item in selected
            if isinstance(item, dict)
        ]

        try:
            job = ProcessingJob.enqueue_advocate_import(request.user, normalized)
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
