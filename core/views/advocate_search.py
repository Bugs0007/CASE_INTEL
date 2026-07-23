"""
Advocate search views: search eCourts by advocate name/bar code (secondary
entry point alongside the existing manual CNR entry in case_tracking.py),
and bulk-import selected results into new Cases.

Search is SYNCHRONOUS -- one CAPTCHA-gated portal call, no case-year
filter exists for this search mode (see ecourts_provider.py's module
docstring), so it fits the same request/response pattern as
CaseTrackingPreviewView. Bulk import is ASYNC (ProcessingJob) -- N
sequential CAPTCHA-gated fetches can run well past a request timeout.
"""

from __future__ import annotations

import re

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AdvocateSearchPreference, ProcessingJob
from core.services.court_data import CourtDataError, get_provider
from core.views.case_tracking import _error_response

_BAR_CODE_RE = re.compile(r"^[A-Za-z]{2,3}/\d+/\d{4}$")
MAX_IMPORT_BATCH = 25


def _validate_district_hierarchy(hierarchy_config: dict) -> str | None:
    required = ["state_code", "dist_code", "court_complex_code"]
    missing = [f for f in required if not hierarchy_config.get(f)]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}."
    return None


class AdvocateSearchView(APIView):
    """Search District Courts cases by advocate name or bar code.

    POST /api/cases/search-advocate/
    Body: {
        "name_or_bar_code": "<name, min 3 chars> or <STATE/NUMBER/YEAR>",
        "court_type": "district",  # "high_court" not yet supported -- see
                                    # ecourts_provider.py's module docstring
        "hierarchy_config": {"state_code", "dist_code",
                              "court_complex_code", "est_code"?},
        "status_filter": "Pending" | "Disposed" | "Both",  # optional, default "Both"
    }
    Returns {"results": [...]} on success (200) -- an empty list is a
    valid, non-error outcome, not a failure. CAPTCHA/timeout failures use
    the same _error_response() mapping as the rest of court-tracking
    (502, retryable -- never a bare 500).
    """

    def post(self, request):
        court_type = request.data.get("court_type")
        if court_type != "district":
            return Response(
                {"detail": "Only District Courts advocate search is supported currently."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hierarchy_config = request.data.get("hierarchy_config") or {}
        error = _validate_district_hierarchy(hierarchy_config)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        name_or_bar_code = (request.data.get("name_or_bar_code") or "").strip()
        status_filter = request.data.get("status_filter") or "Both"
        if status_filter not in ("Pending", "Disposed", "Both"):
            return Response(
                {"detail": "status_filter must be 'Pending', 'Disposed', or 'Both'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        advocate_name = ""
        bar_code = ""
        if _BAR_CODE_RE.match(name_or_bar_code):
            bar_code = name_or_bar_code
        elif len(name_or_bar_code) >= 3:
            advocate_name = name_or_bar_code
        else:
            return Response(
                {
                    "detail": "Enter an advocate name (at least 3 characters) or a bar "
                    "code in STATE/NUMBER/YEAR format (e.g. MAH/1234/2015)."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider = get_provider()
        try:
            results = provider.search_by_advocate(
                hierarchy_config,
                advocate_name=advocate_name,
                bar_code=bar_code,
                status_filter=status_filter,
            )
        except CourtDataError as exc:
            return _error_response(exc)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        AdvocateSearchPreference.objects.update_or_create(
            owner=request.user,
            defaults={"court_type": court_type, "hierarchy_config": hierarchy_config},
        )

        return Response({"results": [r.to_dict() for r in results]}, status=status.HTTP_200_OK)


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

        job = ProcessingJob.enqueue_advocate_import(request.user, normalized)
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
    """The caller's last-used court hierarchy, for pre-filling the search
    page's hierarchy picker.

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
