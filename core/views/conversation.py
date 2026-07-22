"""
Conversation views — list, retrieve, and delete conversations.
"""

from django.db.models import Count, OuterRef, Prefetch, Subquery, TextField
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.views import APIView

from core.models import Conversation, Message
from core.serializers import (
    ConversationDetailSerializer,
    ConversationListSerializer,
    MessageSerializer,
)
from core.services.conversation_utils import (
    build_export_filename,
    build_markdown_transcript,
    build_pdf_transcript,
    build_text_transcript,
)
from core.views.mixins import OwnerScopedMixin


def _conversation_queryset():
    first_user_message = Subquery(
        Message.objects.filter(conversation_id=OuterRef("pk"), role="user")
        .order_by("created_at")
        .values("content")[:1],
        output_field=TextField(),
    )
    ordered_messages = Message.objects.prefetch_related(
        "citations__document",
        "citations__chunk__document",
        "citations__email",
    ).order_by("created_at")
    return (
        Conversation.objects.select_related("case")
        .annotate(
            message_count=Count("messages"),
            first_user_message=first_user_message,
        )
        .prefetch_related(Prefetch("messages", queryset=ordered_messages))
        .order_by("-last_message_at", "-started_at", "-id")
    )


class ConversationListView(OwnerScopedMixin, generics.ListAPIView):
    """List conversations, optionally filtered by case_id.

    GET /api/conversations/
    GET /api/conversations/?case_id=1

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = ConversationListSerializer

    def get_base_queryset(self):
        qs = _conversation_queryset()
        case_id = self.request.query_params.get("case_id")
        if case_id is not None:
            qs = qs.filter(case_id=case_id)
        return qs


class ConversationDetailView(OwnerScopedMixin, generics.RetrieveDestroyAPIView):
    """Retrieve or delete a conversation with its messages.

    GET    /api/conversations/<id>/
    DELETE /api/conversations/<id>/

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = ConversationDetailSerializer
    queryset = _conversation_queryset()


class ConversationMessagesView(OwnerScopedMixin, generics.ListAPIView):
    """Return ordered message history for a conversation.

    GET /api/conversations/<id>/messages/

    Scoped to request.user (OwnerScopedMixin) -- messages always carry the
    same owner as their conversation, so this also correctly returns empty
    for a conversation id that belongs to another user, rather than leaking
    it.
    """

    serializer_class = MessageSerializer

    def get_base_queryset(self):
        return (
            Message.objects.filter(conversation_id=self.kwargs["pk"])
            .prefetch_related(
                "citations__document",
                "citations__chunk__document",
                "citations__email",
            )
            .order_by("created_at")
        )


class ConversationExportView(APIView):
    """Export a conversation transcript.

    GET /api/conversations/<id>/export/?format=txt|md|pdf

    NOTE: this was previously a plain django.views.View, which meant it sat
    OUTSIDE DRF's request/authentication pipeline entirely -- DRF's
    TokenAuthentication only ever runs inside APIView.dispatch(), so
    request.user here was always AnonymousUser and this endpoint was
    reachable with no auth at all regardless of the global
    DEFAULT_PERMISSION_CLASSES setting. Now an APIView, it goes through the
    same TokenAuthentication + IsAuthenticated + owner-scoping as every
    other endpoint.
    """

    def get(self, request, *args, **kwargs):
        conversation = get_object_or_404(
            _conversation_queryset().filter(pk=kwargs["pk"], owner=request.user)
        )
        requested_format = (request.GET.get("format") or "txt").lower()
        export_format = requested_format if requested_format in {"txt", "md", "pdf"} else "txt"

        if export_format == "md":
            content = build_markdown_transcript(conversation).encode("utf-8")
            content_type = "text/markdown; charset=utf-8"
        elif export_format == "pdf":
            content = build_pdf_transcript(conversation)
            content_type = "application/pdf"
        else:
            content = build_text_transcript(conversation).encode("utf-8")
            content_type = "text/plain; charset=utf-8"

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = (
            f'attachment; filename="{build_export_filename(conversation, export_format)}"'
        )
        return response
