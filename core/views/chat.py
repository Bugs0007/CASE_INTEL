"""
Chat view — processes user questions through the LangGraph AI pipeline.
"""

import logging
from typing import Optional

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, Conversation, Message
from core.serializers import ChatRequestSerializer, ChatResponseSerializer
from core.services.ai_workflow import AIWorkflowService

logger = logging.getLogger(__name__)

# Singleton workflow service — lazily initializes its dependencies
_ai_service = AIWorkflowService()


class ChatView(APIView):
    """Process a user question through the LangGraph AI pipeline.

    POST /api/chat/
    {
        "query": "What were the key arguments in the motion to dismiss?",
        "case_id": 1,           // optional
        "conversation_id": 5    // optional
    }
    """

    def post(self, request: Request) -> Response:
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        query: str = serializer.validated_data["query"]
        case_id: Optional[int] = serializer.validated_data.get("case_id")
        conversation_id: Optional[int] = serializer.validated_data.get(
            "conversation_id"
        )

        # Validate case exists when provided
        if case_id is not None and not Case.objects.filter(id=case_id).exists():
            return Response(
                {"detail": f"Case with id {case_id} does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if conversation_id is not None:
            conversation = Conversation.objects.filter(id=conversation_id).first()
            if conversation is None:
                return Response(
                    {"detail": f"Conversation with id {conversation_id} does not exist."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if case_id is not None and conversation.case_id != case_id:
                return Response(
                    {"detail": "The selected conversation does not belong to this case."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        logger.info(
            "Chat request: case=%s, conversation=%s, query='%s...'",
            case_id,
            conversation_id,
            query[:60],
        )

        ai_response = _ai_service.process_query(
            user_query=query,
            case_id=case_id,
            conversation_id=conversation_id,
        )

        # Find the conversation ID from the saved message
        conversation_id_out = None
        if ai_response.message_id:
            msg = Message.objects.filter(id=ai_response.message_id).first()
            if msg:
                conversation_id_out = msg.conversation_id

        response_data = {
            "answer": ai_response.answer,
            "confidence": ai_response.confidence,
            "query_type": ai_response.query_type,
            "requires_clarification": ai_response.requires_clarification,
            "clarification_question": ai_response.clarification_question,
            "message_id": ai_response.message_id,
            "conversation_id": conversation_id_out,
            "citations": ai_response.citations,
        }

        response_serializer = ChatResponseSerializer(data=response_data)
        response_serializer.is_valid(raise_exception=True)

        return Response(response_serializer.validated_data, status=status.HTTP_200_OK)
