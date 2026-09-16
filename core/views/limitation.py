"""Limitation deadline views.

The rules list and the computation are reference data -- no tenant rows.
Recording a deadline is scoped to request.user by hand: another advocate's
case or order is a 404/400, never a way in.
"""

from datetime import date

from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, CourtOrder
from core.serializers import TaskSerializer
from core.services.limitation import (
    LIMITATION_RULES,
    UnknownLimitationRuleError,
    add_limitation_deadline,
    compute_deadline,
    get_rule,
    rules_for_court,
)
from core.services.tasks import OUTCOME_CREATED


class _DeadlineInput(serializers.Serializer):
    rule_key = serializers.ChoiceField(choices=[rule.key for rule in LIMITATION_RULES])
    trigger_date = serializers.DateField()
    source_order = serializers.IntegerField(required=False, allow_null=True)


class LimitationRulesView(APIView):
    """GET /api/limitation/rules/?court_type=high_court -- rules for the picker.

    Without court_type (or with an unknown one), every rule is returned.
    """

    def get(self, request: Request) -> Response:
        rules = rules_for_court(request.query_params.get("court_type"))
        return Response([rule.to_dict() for rule in rules])


class LimitationComputeView(APIView):
    """GET /api/limitation/compute/?rule_key=review&trigger_date=2026-09-01

    The last day and its notes, without recording anything -- for showing
    the date before the advocate adds it.
    """

    def get(self, request: Request) -> Response:
        try:
            rule = get_rule(request.query_params.get("rule_key", ""))
        except UnknownLimitationRuleError as exc:
            return Response({"rule_key": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            trigger_date = date.fromisoformat(request.query_params.get("trigger_date", ""))
        except ValueError:
            return Response(
                {"trigger_date": ["Expected a date as YYYY-MM-DD."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(compute_deadline(rule, trigger_date).to_dict())


class CaseLimitationDeadlineView(APIView):
    """POST /api/cases/<id>/limitation-deadlines/

    Body: {"rule_key": "...", "trigger_date": "YYYY-MM-DD", "source_order": <order id, optional>}
    Records the deadline as a Task on the case: 201 when created, 200 when
    the same rule and date were already recorded.
    """

    def post(self, request: Request, pk: int) -> Response:
        case = Case.objects.filter(id=pk, owner=request.user).first()
        if case is None:
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)

        payload = _DeadlineInput(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        source_order = None
        if data.get("source_order") is not None:
            source_order = CourtOrder.objects.filter(
                id=data["source_order"], case=case, owner=request.user
            ).first()
            if source_order is None:
                return Response(
                    {"source_order": ["That order is not on this case."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        task, outcome, computation = add_limitation_deadline(
            case,
            rule_key=data["rule_key"],
            trigger_date=data["trigger_date"],
            source_order=source_order,
        )
        return Response(
            {
                "task": TaskSerializer(task).data,
                "computation": computation.to_dict(),
                "outcome": outcome,
            },
            status=status.HTTP_201_CREATED if outcome == OUTCOME_CREATED else status.HTTP_200_OK,
        )
