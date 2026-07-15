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
    TrackingNotEnabledError,
    latest_snapshot,
    refresh_case_tracking,
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


class CaseTrackingSetupView(APIView):
    """Save tracking_config, enable tracking, and run the first fetch.

    POST /api/cases/<id>/tracking/
    Body: the tracking_config shape CourtDataProvider.fetch_case() expects,
    e.g. {"court_type": "district", "state_code": "29", "dist_code": "2",
    "court_complex_code": "1290019", "est_code": "2", "case_type": "2^2",
    "case_number": "300", "year": "2024"}
    """

    def post(self, request, pk):
        try:
            case = Case.objects.get(pk=pk)
        except Case.DoesNotExist:
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)

        tracking_config = request.data
        court_type = tracking_config.get("court_type")
        if court_type not in ("district", "high_court"):
            return Response(
                {"detail": "tracking_config.court_type must be 'district' or 'high_court'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        required = ["case_type", "case_number", "year"]
        required += (
            ["state_code", "dist_code", "court_complex_code"]
            if court_type == "district"
            else ["hc_court_code"]
        )
        missing = [f for f in required if not tracking_config.get(f)]
        if missing:
            return Response(
                {"detail": f"Missing required field(s): {', '.join(missing)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        case.court_type = court_type
        case.tracking_config = dict(tracking_config)
        case.tracking_enabled = True
        case.save(update_fields=["court_type", "tracking_config", "tracking_enabled"])

        try:
            result = refresh_case_tracking(case, force=True)
        except CourtDataError as exc:
            # Setup failed the first lookup -- leave tracking_enabled=True
            # (the config was valid enough to attempt) but report the
            # actionable reason so the user can fix case number/year and
            # retry via the refresh endpoint.
            case.refresh_from_db()
            return _error_response(exc)

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
