"""Hearing prep sheet views.

Plain APIViews scoped to request.user by hand: every lookup goes through
_own_hearing, so another advocate's hearing id is a 404, indistinguishable
from one that doesn't exist.
"""

import re

from django.http import HttpResponse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Hearing
from core.serializers.hearing_digest import serialize_hearing_digest
from core.services.hearing_digest import (
    assemble_hearing_digest,
    get_briefing_state,
    request_briefing,
)
from core.services.hearing_digest.pdf import render_hearing_digest_pdf

_NOT_FOUND = {"detail": "Hearing not found."}


def _own_hearing(request: Request, pk: int) -> Hearing | None:
    return Hearing.objects.select_related("case").filter(id=pk, owner=request.user).first()


def _digest_data(hearing: Hearing) -> dict:
    return serialize_hearing_digest(
        assemble_hearing_digest(hearing), get_briefing_state(hearing.case)
    )


class HearingDigestView(APIView):
    """GET /api/hearings/<id>/digest/ -- the prep sheet for one hearing.

    Reading it never calls the LLM: the briefing paragraph comes from its
    cache, with a status saying whether it is current (see
    core/services/hearing_digest/briefing.py).
    """

    def get(self, request: Request, pk: int) -> Response:
        hearing = _own_hearing(request, pk)
        if hearing is None:
            return Response(_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response(_digest_data(hearing))


class HearingDigestPdfView(APIView):
    """GET /api/hearings/<id>/digest/pdf/ -- the prep sheet as a PDF.

    A separate path rather than ?format=pdf: DRF reads a `format` query
    parameter as a renderer override and 404s before the view runs.
    """

    def get(self, request: Request, pk: int) -> HttpResponse:
        hearing = _own_hearing(request, pk)
        if hearing is None:
            return Response(_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        pdf = render_hearing_digest_pdf(_digest_data(hearing))
        case_ref = re.sub(r"[^A-Za-z0-9]+", "-", hearing.case.case_number).strip("-") or "case"
        filename = f"prep-{case_ref}-{hearing.hearing_date.date().isoformat()}.pdf"
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class HearingDigestBriefingView(APIView):
    """POST /api/hearings/<id>/digest/briefing/ -- (re)generate the paragraph.

    Enqueues a case_briefing job when the paragraph is missing, stale or
    failed: 202 with the new state. Otherwise nothing is queued: 200 with
    the current state.
    """

    def post(self, request: Request, pk: int) -> Response:
        hearing = _own_hearing(request, pk)
        if hearing is None:
            return Response(_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        state, enqueued = request_briefing(hearing.case)
        return Response(
            state, status=status.HTTP_202_ACCEPTED if enqueued else status.HTTP_200_OK
        )
