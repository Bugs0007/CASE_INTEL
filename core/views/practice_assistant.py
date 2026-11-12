"""The dashboard practice assistant: an overview read and a read-only chat.

Both are plain APIViews scoped by hand: the owner of every read and write is
`request.user`, never anything in the request. Both answer 404 while
settings.PRACTICE_ASSISTANT_ENABLED is off.
"""

import logging
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case
from core.serializers.practice_assistant import DAY_FORMAT, PracticeChatRequestSerializer
from core.services.graph.practice_graph import run_practice_turn
from core.services.india_time import india_now
from core.services.practice_assistant import reads, turns
from core.services.practice_assistant.contracts import DEFAULT_RANGE_DAYS, MAX_RANGE_DAYS

logger = logging.getLogger(__name__)


def _require_enabled() -> None:
    if not getattr(settings, "PRACTICE_ASSISTANT_ENABLED", False):
        raise NotFound()


def _day_param(request: Request, name: str):
    raw = request.query_params.get(name)
    if raw in (None, ""):
        return None
    try:
        return datetime.strptime(raw, DAY_FORMAT).date()
    except ValueError:
        raise ValidationError({"detail": f"'{name}' must be a date in YYYY-MM-DD format."})


class PracticeOverviewView(APIView):
    """GET /api/practice-assistant/overview/?from=YYYY-MM-DD&to=YYYY-MM-DD&case_page=N

    `from` defaults to India today, `to` to `from` + 6 days, `case_page` to 1.
    """

    def get(self, request: Request) -> Response:
        _require_enabled()
        now = india_now()
        date_from = _day_param(request, "from") or now.date()
        date_to = _day_param(request, "to") or date_from + timedelta(days=DEFAULT_RANGE_DAYS - 1)
        if date_to < date_from:
            raise ValidationError({"detail": "'to' cannot be before 'from'."})
        if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
            raise ValidationError({"detail": f"The range can cover at most {MAX_RANGE_DAYS} days."})
        raw_page = request.query_params.get("case_page") or "1"
        if not raw_page.isascii() or not raw_page.isdigit() or int(raw_page) < 1:
            raise ValidationError({"detail": "'case_page' must be a whole number, 1 or more."})

        owner = request.user
        return Response(
            {
                "portfolio": reads.portfolio_snapshot(owner=owner, page=int(raw_page), now=now),
                "calendar": reads.calendar_window(
                    owner=owner, date_from=date_from, date_to=date_to, now=now
                ),
            }
        )


class PracticeChatView(APIView):
    """POST /api/practice-assistant/chat/

    {"query": "...", "client_request_id": "...", "conversation_id": 5,
     "selected_day": "2026-11-12", "case_id": 3}   (the last three optional)

    Answers with a PracticeTurn. Sending the same client_request_id again
    returns the stored turn and writes nothing. A turn that fails with an
    error stores nothing (the transaction rolls back), so it can be resent.
    """

    def post(self, request: Request) -> Response:
        _require_enabled()
        serializer = PracticeChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner = request.user
        conversation_id = data.get("conversation_id")
        case_id = data.get("case_id")
        started = time.monotonic()

        with transaction.atomic():
            turns.lock_owner(owner.id)

            conversation = None
            if conversation_id is not None:
                # Another owner's conversation, a case or legacy one, and an
                # id that does not exist are all the same 404.
                conversation = turns.find_practice_conversation(owner, conversation_id)
                if conversation is None:
                    raise NotFound(f"Conversation with id {conversation_id} does not exist.")
            if case_id is not None and not Case.objects.filter(id=case_id, owner=owner).exists():
                raise NotFound(f"Case with id {case_id} does not exist.")

            replay = turns.find_replay(owner, data["client_request_id"])
            if replay is not None:
                logger.info("Practice turn replayed: conversation=%s", replay["conversation_id"])
                return Response(replay, status=status.HTTP_200_OK)

            result = run_practice_turn(
                owner=owner,
                query=data["query"],
                now=india_now(),
                selected_day=data.get("selected_day"),
                case_id=case_id,
            )
            turn = turns.store_turn(
                owner=owner,
                conversation=conversation,
                query=data["query"],
                client_request_id=data["client_request_id"],
                result=result,
            )

        # Metadata only: never the question or the answer.
        logger.info(
            "Practice turn: conversation=%s intent=%s status=%s routed_by=%s llm_calls=%d "
            "sources=%d candidates=%d duration_ms=%d",
            turn["conversation_id"],
            turn["intent"],
            turn["status"],
            result.get("routed_by"),
            result.get("llm_calls", 0),
            len(turn["sources"]),
            len(turn["case_candidates"]),
            int((time.monotonic() - started) * 1000),
        )
        return Response(turn, status=status.HTTP_200_OK)
