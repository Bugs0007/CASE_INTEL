"""
REST API views for the Case Intel application.

Provides endpoints for:
    - Chat: Send queries to the LangGraph AI pipeline
    - Conversations: List, retrieve, and delete conversations
    - Cases: CRUD operations on legal cases
    - Documents: CRUD + upload + processing trigger
"""

import logging
import os
from typing import Optional

from django.conf import settings as django_settings
from django.db.models import Count
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, Conversation, Document, Message
from core.serializers import (
    CaseSerializer,
    ChatRequestSerializer,
    ChatResponseSerializer,
    ConversationDetailSerializer,
    ConversationListSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
)
from core.services.ai_workflow import AIWorkflowService

logger = logging.getLogger(__name__)

# Singleton workflow service — lazily initializes its dependencies
_ai_service = AIWorkflowService()


# ======================================================================
# Chat
# ======================================================================


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


# ======================================================================
# Conversations
# ======================================================================


class ConversationListView(generics.ListAPIView):
    """List conversations, optionally filtered by case_id.

    GET /api/conversations/
    GET /api/conversations/?case_id=1
    """

    serializer_class = ConversationListSerializer

    def get_queryset(self):
        qs = Conversation.objects.annotate(message_count=Count("messages"))
        case_id = self.request.query_params.get("case_id")
        if case_id is not None:
            qs = qs.filter(case_id=case_id)
        return qs


class ConversationDetailView(generics.RetrieveDestroyAPIView):
    """Retrieve or delete a conversation with its messages.

    GET    /api/conversations/<id>/
    DELETE /api/conversations/<id>/
    """

    serializer_class = ConversationDetailSerializer
    queryset = Conversation.objects.prefetch_related("messages__citations")


# ======================================================================
# Cases
# ======================================================================


class CaseListCreateView(generics.ListCreateAPIView):
    """List or create cases.

    GET  /api/cases/
    POST /api/cases/
    """

    serializer_class = CaseSerializer
    queryset = Case.objects.all()


class CaseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a case.

    GET    /api/cases/<id>/
    PATCH  /api/cases/<id>/
    DELETE /api/cases/<id>/
    """

    serializer_class = CaseSerializer
    queryset = Case.objects.all()


# ======================================================================
# Documents
# ======================================================================


class DocumentListView(generics.ListAPIView):
    """List documents, optionally filtered by case_id.

    GET /api/documents/
    GET /api/documents/?case_id=1
    """

    serializer_class = DocumentSerializer

    def get_queryset(self):
        qs = Document.objects.select_related("case")
        case_id = self.request.query_params.get("case_id")
        if case_id is not None:
            qs = qs.filter(case_id=case_id)
        return qs


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    """Retrieve or delete a document.

    GET    /api/documents/<id>/
    DELETE /api/documents/<id>/
    """

    serializer_class = DocumentSerializer
    queryset = Document.objects.select_related("case")


class DocumentUploadView(APIView):
    """Upload a document file and trigger processing.

    POST /api/documents/upload/  (multipart/form-data)
    Fields:
        file          - the document file
        case_id       - optional case to associate with
        document_type - optional type classification
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        case_id = serializer.validated_data.get("case_id")
        document_type = serializer.validated_data.get("document_type", "other")

        # Validate case exists when provided
        if case_id is not None and not Case.objects.filter(id=case_id).exists():
            return Response(
                {"detail": f"Case with id {case_id} does not exist."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Determine file type from extension
        filename = uploaded_file.name
        file_type = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        # Save file to media directory
        upload_dir = os.path.join(django_settings.BASE_DIR, "media", "documents")
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, filename)

        # Avoid overwriting existing files
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(file_path):
            file_path = os.path.join(upload_dir, f"{base}_{counter}{ext}")
            counter += 1

        with open(file_path, "wb") as dest:
            for chunk in uploaded_file.chunks():
                dest.write(chunk)

        # Create document record
        document = Document.objects.create(
            case_id=case_id,
            filename=filename,
            file_path=file_path,
            file_type=file_type,
            file_size=uploaded_file.size,
            document_type=document_type,
            processing_status="pending",
        )

        logger.info("Document uploaded: id=%d, filename=%s", document.id, filename)

        return Response(
            DocumentSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentProcessView(APIView):
    """Trigger processing for a document (extract text, chunk, embed).

    POST /api/documents/<id>/process/
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            document = Document.objects.get(id=pk)
        except Document.DoesNotExist:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if document.processing_status == "processing":
            return Response(
                {"detail": "Document is already being processed."},
                status=status.HTTP_409_CONFLICT,
            )

        from core.services.document_processor import DocumentProcessor

        processor = DocumentProcessor()

        try:
            document = processor.process_document(document.id)
        except Exception as exc:
            logger.exception("Document processing failed: %d", pk)
            return Response(
                {"detail": f"Processing failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(DocumentSerializer(document).data, status=status.HTTP_200_OK)
