"""Task views -- the one list of everything due on the advocate's cases."""

from datetime import date

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from core.models import Task
from core.serializers import TaskSerializer
from core.views.mixins import OwnerScopedMixin

_TASK_QUERYSET = Task.objects.select_related("case")


def _parse_date_param(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: "Expected a date as YYYY-MM-DD."}) from None


class TaskListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """List or create tasks.

    GET  /api/tasks/
    GET  /api/tasks/?case_id=1
    GET  /api/tasks/?status=open          -- pending or in progress
    GET  /api/tasks/?status=completed
    GET  /api/tasks/?kind=order_direction
    GET  /api/tasks/?due_before=2026-10-01 -- dated tasks due on or before (any status;
                                            add status=open for what's outstanding)
    GET  /api/tasks/?overdue=true         -- open and past due
    GET  /api/tasks/?needs_review=true
    POST /api/tasks/                      -- always a manual task

    Scoped to request.user (OwnerScopedMixin). A case_id belonging to
    another user yields an empty list, since the owner filter applies last.
    Ordered by due date (undated last), then creation.
    """

    serializer_class = TaskSerializer

    def get_base_queryset(self):
        qs = _TASK_QUERYSET
        params = self.request.query_params

        case_id = params.get("case_id")
        if case_id:
            qs = qs.filter(case_id=case_id)

        status_param = params.get("status")
        if status_param == "open":
            qs = qs.filter(status__in=Task.OPEN_STATUSES)
        elif status_param:
            qs = qs.filter(status=status_param)

        kind = params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)

        needs_review = params.get("needs_review")
        if needs_review in ("true", "false"):
            qs = qs.filter(needs_review=needs_review == "true")

        due_before = params.get("due_before")
        if due_before:
            qs = qs.filter(due_date__lte=_parse_date_param(due_before, "due_before"))

        if params.get("overdue") == "true":
            qs = qs.filter(
                status__in=Task.OPEN_STATUSES, due_date__lt=timezone.localdate()
            )

        return qs


class TaskDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a task.

    GET    /api/tasks/<id>/
    PATCH  /api/tasks/<id>/
    DELETE /api/tasks/<id>/   -- manual tasks only

    A system-generated task (from a court order or a limitation rule) can't
    be deleted: its source would recreate it on the next regeneration.
    Dismiss it instead (PATCH status=cancelled), which the generators
    respect permanently.

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = TaskSerializer
    queryset = _TASK_QUERYSET

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        if task.is_system_generated:
            return Response(
                {
                    "detail": (
                        "This task was generated from the case record. Dismiss it "
                        "instead of deleting it, so it isn't recreated."
                    ),
                    "code": "system_task_not_deletable",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)
