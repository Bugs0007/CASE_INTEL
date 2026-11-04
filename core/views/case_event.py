"""Case event views -- the advocate's own appointments on their cases."""

from datetime import date

from rest_framework import generics
from rest_framework.exceptions import ValidationError

from core.models import CaseEvent
from core.serializers import CaseEventSerializer
from core.views.mixins import OwnerScopedMixin

_EVENT_QUERYSET = CaseEvent.objects.select_related("case")


def _parse_date_param(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: "Expected a date as YYYY-MM-DD."}) from None


class CaseEventListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """List or create case events.

    GET  /api/case-events/
    GET  /api/case-events/?case_id=1
    GET  /api/case-events/?date_from=2026-11-01&date_to=2026-11-30   (inclusive)
    GET  /api/case-events/?status=scheduled
    POST /api/case-events/

    Scoped to request.user (OwnerScopedMixin). A case_id belonging to another
    user yields an empty list, since the owner filter applies last.
    """

    serializer_class = CaseEventSerializer

    def get_base_queryset(self):
        qs = _EVENT_QUERYSET
        params = self.request.query_params

        case_id = params.get("case_id")
        if case_id:
            qs = qs.filter(case_id=case_id)

        date_from = params.get("date_from")
        if date_from:
            qs = qs.filter(date__gte=_parse_date_param(date_from, "date_from"))

        date_to = params.get("date_to")
        if date_to:
            qs = qs.filter(date__lte=_parse_date_param(date_to, "date_to"))

        status_param = params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        return qs


class CaseEventDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a case event.

    GET / PATCH / DELETE /api/case-events/<id>/

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = CaseEventSerializer
    queryset = _EVENT_QUERYSET
