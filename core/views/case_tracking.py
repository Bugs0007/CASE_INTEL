"""
Court tracking views: hierarchy discovery for the setup form, tracking
setup (first fetch), and re-fetch.

All error handling here maps CourtDataError subclasses to actionable
4xx responses -- a failed lookup during setup is an expected, common
outcome (wrong case number, case not in this court), not a server error.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, Hearing
from core.serializers import CaseSerializer, HearingSerializer
from core.services.court_data import CaptchaSolveError, CaseNotFoundError, CourtDataError, CourtPortalError, get_provider
from core.services.court_data.ecourts_provider import parse_complex_code
from core.services.court_tracking import (
    MissingTrackingConfigError,
    PreviewExpiredError,
    PreviewThrottledError,
    TrackingNotEnabledError,
    confirm_case_tracking,
    latest_snapshot,
    preview_case_tracking,
    refresh_case_tracking,
    untrack_case,
)


def _error_response(exc: Exception) -> Response:
    """Map a court-data exception to an actionable 4xx response."""
    if isinstance(exc, CaseNotFoundError):
        return Response({"detail": str(exc), "code": "case_not_found"}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(exc, CaptchaSolveError):
        return Response(
            {"detail": "The court portal's CAPTCHA could not be solved after several attempts. Please try again.", "code": "captcha_failed"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, CourtPortalError):
        return Response(
            {"detail": f"The court portal could not be reached: {exc}", "code": "portal_error"},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, CourtDataError):
        return Response({"detail": str(exc), "code": "court_data_error"}, status=status.HTTP_400_BAD_REQUEST)
    raise exc


def _validate_tracking_config(tracking_config: dict) -> str | None:
    """Returns an error message if tracking_config is invalid for either
    the CNR-first shape ({court_type, cnr}) or the cascade fallback shape
    (court hierarchy + case_type/case_number/year), else None."""
    court_type = tracking_config.get("court_type")
    if court_type not in ("district", "high_court"):
        return "tracking_config.court_type must be 'district' or 'high_court'."

    cnr = tracking_config.get("cnr")
    if cnr:
        if not isinstance(cnr, str) or len(cnr) != 16 or not cnr.isalnum():
            return "cnr must be a 16-character alphanumeric CNR number."
        return None

    required = ["case_type", "case_number", "year"]
    required += (
        ["state_code", "dist_code", "court_complex_code"]
        if court_type == "district"
        else ["hc_court_code"]
    )
    missing = [f for f in required if not tracking_config.get(f)]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}."
    return None


def _snapshot_response(case: Case, data=None) -> dict:
    """Common response shape for tracking setup/refresh: the updated
    Case, its eCourts-sourced hearings, and the latest data snapshot."""
    snapshot = latest_snapshot(case) if data is None else None
    return {
        "case": CaseSerializer(case).data,
        "hearings": HearingSerializer(
            Hearing.objects.filter(case=case, source="ecourts").order_by("hearing_date"), many=True
        ).data,
        "snapshot": snapshot
        or (
            {
                "cnr": data.cnr,
                "case_status": data.case_status,
                "case_stage": data.case_stage,
                "court_and_judge": data.court_and_judge,
                "court_name": data.court_name,
                "next_hearing_date": data.next_hearing_date.isoformat() if data.next_hearing_date else None,
                "first_hearing_date": data.first_hearing_date.isoformat() if data.first_hearing_date else None,
                "nature_of_disposal": data.nature_of_disposal,
                "hearing_count": len(data.hearing_history),
            }
            if data is not None
            else None
        ),
    }


class CourtStructureView(APIView):
    """Cached court-hierarchy discovery for the tracking setup form.

    GET /api/court-structure/?court_type=district
        -> states
    GET /api/court-structure/?court_type=district&state_code=29
        -> districts
    GET /api/court-structure/?court_type=district&state_code=29&dist_code=2
        -> court complexes (value/label pairs; value is the raw portal
           "code@est_codes@flag" -- see complex_code/est_code in the
           parsed response for what to actually submit)
    GET /api/court-structure/?court_type=district&state_code=29&dist_code=2
            &court_complex_code=1290019&est_code=2
        -> case types (submit the returned code as-is; District Courts
           codes are compound "<code>^<est_code>" strings)

    GET /api/court-structure/?court_type=high_court
        -> High Courts
    GET /api/court-structure/?court_type=high_court&hc_court_code=telangana
        -> benches
    GET /api/court-structure/?court_type=high_court&hc_court_code=telangana&bench_code=1
        -> case types
    """

    def get(self, request):
        court_type = request.query_params.get("court_type")
        if court_type not in ("district", "high_court"):
            return Response(
                {"detail": "court_type must be 'district' or 'high_court'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        provider = get_provider()

        try:
            if court_type == "district":
                return self._district_structure(provider, request)
            return self._hc_structure(provider, request)
        except CourtDataError as exc:
            return _error_response(exc)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def _district_structure(self, provider, request):
        state_code = request.query_params.get("state_code")
        dist_code = request.query_params.get("dist_code")
        court_complex_code = request.query_params.get("court_complex_code")

        if not state_code:
            return Response({"level": "state", "options": provider.list_court_options("district")})
        if not dist_code:
            return Response({"level": "district", "options": provider.list_districts(state_code)})
        if not court_complex_code:
            raw = provider.list_complexes(state_code, dist_code)
            parsed = {
                value: {"label": label, **dict(zip(("complex_code", "est_code"), parse_complex_code(value)))}
                for value, label in raw.items()
            }
            return Response({"level": "complex", "options": parsed})

        est_code = request.query_params.get("est_code", "")
        options = provider.list_case_types(
            "district",
            state_code=state_code,
            dist_code=dist_code,
            court_complex_code=court_complex_code,
            est_code=est_code,
        )
        return Response({"level": "case_type", "options": options})

    def _hc_structure(self, provider, request):
        hc_court_code = request.query_params.get("hc_court_code")
        bench_code = request.query_params.get("bench_code")

        if not hc_court_code:
            return Response({"level": "court", "options": provider.list_court_options("high_court")})
        if not bench_code:
            return Response({"level": "bench", "options": provider.list_benches(hc_court_code)})

        options = provider.list_case_types(
            "high_court", hc_court_code=hc_court_code, bench_code=bench_code
        )
        return Response({"level": "case_type", "options": options})


class CaseTrackingView(APIView):
    """Untrack a case: DELETE /api/cases/<id>/tracking/.

    Clears cnr_number/tracking_config/tracking_enabled/fetch_status AND
    last_fetched_at (so a wrong case's fetch doesn't rate-limit re-tracking
    the right one -- see untrack_case() docstring), deletes source='ecourts'
    Hearing rows (manual hearings untouched), and logs an ActivityLog entry.
    This is the recovery path when setup was confirmed against the wrong
    case: untrack, then preview/confirm again with corrected inputs.
    """

    def delete(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)

        untrack_case(case)
        case.refresh_from_db()
        return Response(CaseSerializer(case).data, status=status.HTTP_200_OK)


class CaseTrackingPreviewView(APIView):
    """Fetch live court data WITHOUT persisting it -- the human-confirmation
    step. POST /api/cases/<id>/tracking/preview/

    Body: either the CNR-first shape {"court_type": "district"|"high_court",
    "cnr": "<16-char CNR>"}, or the cascade fallback shape (court hierarchy
    + case_type/case_number/year -- same shape the old one-step setup
    endpoint took). Returns the fetched case identity (title, parties, CNR,
    court name, status) and a preview_token to pass to .../confirm/.
    Nothing is written to the case; exempt from the per-case 1h rate limit
    but subject to a per-user preview throttle.
    """

    def post(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)

        tracking_config = dict(request.data)
        error = _validate_tracking_config(tracking_config)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        try:
            preview = preview_case_tracking(case, tracking_config, user_id=request.user.id)
        except PreviewThrottledError as exc:
            return Response({"detail": str(exc), "code": "preview_throttled"}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except CourtDataError as exc:
            return _error_response(exc)

        return Response(preview, status=status.HTTP_200_OK)


class CaseTrackingConfirmView(APIView):
    """Persist a previously-previewed fetch. POST /api/cases/<id>/tracking/confirm/

    Body: {"preview_token": "..."}. Loads ONLY the server-cached payload
    from the matching preview call -- never trusts client-supplied case
    data -- and sets cnr_number/tracking_config/tracking_enabled, creates
    Hearing rows, and logs a CourtFetchLog, exactly like the old one-step
    setup used to, but now only after a human has seen the preview.
    """

    def post(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)

        preview_token = request.data.get("preview_token")
        if not preview_token:
            return Response({"detail": "preview_token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            result = confirm_case_tracking(case, preview_token, user_id=request.user.id)
        except PreviewExpiredError as exc:
            return Response({"detail": str(exc), "code": "preview_expired"}, status=status.HTTP_410_GONE)

        case.refresh_from_db()
        return Response(_snapshot_response(case, result["data"]), status=status.HTTP_201_CREATED)


class CaseTrackingRefreshView(APIView):
    """Re-fetch live court data for an already-tracked case.

    POST /api/cases/<id>/tracking/refresh/
    Body (optional): {"force": true} -- only honored for staff users;
    silently ignored otherwise so a non-staff user can't bypass the
    rate limit by just sending the flag.
    """

    def post(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)

        requested_force = bool(request.data.get("force"))
        force = requested_force and bool(request.user and request.user.is_staff)

        try:
            result = refresh_case_tracking(case, force=force)
        except TrackingNotEnabledError:
            return Response(
                {"detail": "Court tracking is not enabled for this case. Set it up first.", "code": "tracking_not_enabled"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except MissingTrackingConfigError:
            return Response(
                {"detail": "This case has no tracking configuration saved.", "code": "missing_config"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except CourtDataError as exc:
            case.refresh_from_db()
            error_resp = _error_response(exc)
            error_resp.data["case"] = CaseSerializer(case).data
            return error_resp

        case.refresh_from_db()

        if result["rate_limited"]:
            payload = _snapshot_response(case)
            payload["rate_limited"] = True
            payload["retry_after"] = result["retry_after"]
            return Response(payload, status=status.HTTP_200_OK)

        payload = _snapshot_response(case, result["data"])
        payload["rate_limited"] = False
        payload["new_hearing_dates"] = [d.isoformat() for d in result["new_hearing_dates"]]
        return Response(payload, status=status.HTTP_200_OK)
