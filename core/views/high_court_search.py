"""High Courts for the advocate search's High Courts tab.

    GET /api/cases/high-courts/                 the courts, from the library registry
    GET /api/cases/high-courts/<code>/benches/  one court's benches, from the portal

Both are public court data, the same for every advocate (no tenant rows), so
they only need a signed-in user.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.services.court_data import CourtDataError, get_provider
from core.services.high_court_registry import get_high_court, high_courts, is_default_bench


class HighCourtListView(APIView):
    """The 25 High Courts, each with its registry benches and whether the
    advocate search can be pointed at it (`supported`, with the reason when not)."""

    def get(self, request):
        return Response({"courts": high_courts()}, status=status.HTTP_200_OK)


class HighCourtBenchesView(APIView):
    """A court's benches as the portal lists them, with the codes the search
    needs. Several courts have more than the registry names (Bombay has seven
    codes); `default` marks the ones that start ticked. The portal call is
    CAPTCHA-free and cached for 30 days like the other court-structure lookups."""

    def get(self, request, code):
        court = get_high_court(code)
        if court is None:
            return Response({"detail": "Unknown High Court."}, status=status.HTTP_404_NOT_FOUND)
        try:
            benches = get_provider().list_benches(court["code"])
        except CourtDataError as exc:
            return Response(
                {"detail": f"The court portal could not list this court's benches: {exc}", "code": "portal_error"},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response(
            {
                "court": court,
                "benches": [
                    {
                        "code": str(bench_code),
                        "name": name,
                        "default": is_default_bench(bench_code, name, court["registry_benches"]),
                    }
                    for bench_code, name in benches.items()
                ],
            },
            status=status.HTTP_200_OK,
        )
