"""The dashboard's "Refresh all tracked cases" button
(core/services/bulk_refresh.py).

All three views are OwnerScopedMixin over ProcessingJob, restricted to
tracking_refresh jobs, so a job id belonging to another advocate is a 404.
The run is a chain of jobs (one per batch); the id the frontend holds is
the first one, and status/cancel follow the chain from there.
"""

from rest_framework import generics, status
from rest_framework.response import Response

from core.models import JobAlreadyRunningError, ProcessingJob
from core.services import bulk_refresh
from core.views.mixins import OwnerScopedMixin

_RUNS = ProcessingJob.objects.filter(job_type="tracking_refresh")


class TrackingRefreshView(OwnerScopedMixin, generics.GenericAPIView):
    """POST /api/cases/refresh-all/  -- start a run (202)
    GET  /api/cases/refresh-all/  -- the caller's latest run, so a reloaded
                                     dashboard can pick up the progress bar
    """

    queryset = _RUNS

    def _latest_root(self):
        # A follow-on job carries root_job_id; the run's own first job doesn't.
        return (
            self.get_queryset()
            .exclude(payload__has_key="root_job_id")
            .order_by("-created_at", "-id")
            .first()
        )

    def get(self, request, *args, **kwargs):
        root = self._latest_root()
        if root is None:
            return Response({"job_id": None})
        return Response(bulk_refresh.run_status(root))

    def post(self, request, *args, **kwargs):
        try:
            job = bulk_refresh.start_bulk_refresh(request.user)
        except bulk_refresh.NothingToRefreshError as exc:
            return Response({"detail": str(exc), "code": "nothing_to_refresh"}, status=status.HTTP_400_BAD_REQUEST)
        except JobAlreadyRunningError as exc:
            body = {"detail": str(exc), "code": "already_running"}
            # Only point at the running job if it is the caller's own; never
            # leak another advocate's job id.
            root = self._latest_root()
            if root is not None and bulk_refresh.run_status(root)["status"] in ("queued", "running"):
                body["job_id"] = root.id
            return Response(body, status=status.HTTP_409_CONFLICT)
        return Response(bulk_refresh.run_status(job), status=status.HTTP_202_ACCEPTED)


class TrackingRefreshStatusView(OwnerScopedMixin, generics.GenericAPIView):
    """GET /api/cases/refresh-all/<id>/"""

    queryset = _RUNS

    def get(self, request, *args, **kwargs):
        return Response(bulk_refresh.run_status(self.get_object()))


class TrackingRefreshCancelView(OwnerScopedMixin, generics.GenericAPIView):
    """POST /api/cases/refresh-all/<id>/cancel/ -- stops after the case in
    progress; cases already refreshed stay refreshed."""

    queryset = _RUNS

    def post(self, request, *args, **kwargs):
        root = self.get_object()
        bulk_refresh.cancel_run(root)
        return Response(bulk_refresh.run_status(root))
