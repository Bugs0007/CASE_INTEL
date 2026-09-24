"""Client-message drafts (case updates, payment reminders) and the
sent-message audit log.

Drafts are written by the system and sent only from here, by the advocate.
All views use OwnerScopedMixin; the action views are GenericAPIViews whose
get_object() goes through the owner-scoped queryset, so another advocate's
message is a 404 exactly like a missing one.
"""

import logging

from rest_framework import generics, status
from rest_framework.response import Response

from core.models import ClientMessage, SentMessage
from core.serializers.client import ClientMessageSerializer, SentMessageSerializer
from core.services import client_updates
from core.services.email_delivery import (
    DeliveryError,
    MissingAdvocateNameError,
    MissingContactEmailError,
)
from core.views.mixins import OwnerScopedMixin

logger = logging.getLogger(__name__)

MAX_LIST = 200

_MESSAGE_QS = ClientMessage.objects.select_related("case", "fee", "hearing")


class ClientMessageListView(OwnerScopedMixin, generics.ListAPIView):
    """GET /api/client-messages/?status=draft&case_id=1&kind=case_update

    Newest first, at most MAX_LIST rows.
    """

    serializer_class = ClientMessageSerializer

    def get_base_queryset(self):
        qs = _MESSAGE_QS
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("case_id"):
            qs = qs.filter(case_id=params["case_id"])
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        return qs

    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()[:MAX_LIST]
        return Response(self.get_serializer(rows, many=True).data)


class ClientMessageDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """GET /api/client-messages/<id>/
    PATCH  -- subject / body / recipient_contact_ids, drafts only
    DELETE -- discards the draft (kept, so it isn't generated again)
    """

    serializer_class = ClientMessageSerializer
    queryset = _MESSAGE_QS

    def update(self, request, *args, **kwargs):
        message = self.get_object()
        if message.status != ClientMessage.STATUS_DRAFT:
            return Response(
                {"detail": "Only a draft can be edited.", "code": "not_a_draft"},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = self.get_serializer(message, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        contact_ids = data.pop("recipient_contact_ids", None)
        if contact_ids is not None:
            try:
                client_updates.set_recipients(message, contact_ids)
            except client_updates.ClientMessageError as exc:
                return Response({"recipient_contact_ids": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        changed = [f for f in ("subject", "body") if f in data and data[f] != getattr(message, f)]
        if changed:
            for f in changed:
                setattr(message, f, data[f])
            message.edited_by_user = True
            message.save(update_fields=[*changed, "edited_by_user", "updated_at"])

        message.refresh_from_db()
        return Response(self.get_serializer(message).data)

    def destroy(self, request, *args, **kwargs):
        message = self.get_object()
        try:
            client_updates.discard_client_message(message)
        except client_updates.NotADraftError as exc:
            return Response({"detail": str(exc), "code": "not_a_draft"}, status=status.HTTP_409_CONFLICT)
        return Response(self.get_serializer(message).data)


class ClientMessageSendView(OwnerScopedMixin, generics.GenericAPIView):
    """POST /api/client-messages/<id>/send/

    200 with sent=false (not an error) when email isn't configured -- the
    message is logged instead, and the response names the env vars needed
    for real delivery. Same contract as the invoice send.
    """

    serializer_class = ClientMessageSerializer
    queryset = _MESSAGE_QS

    def post(self, request, *args, **kwargs):
        message = self.get_object()
        try:
            result = client_updates.send_client_message(message, user=request.user)
        except client_updates.NotADraftError as exc:
            return Response({"detail": str(exc), "code": "not_a_draft"}, status=status.HTTP_409_CONFLICT)
        except client_updates.InvoiceAlreadyPaidError as exc:
            return Response({"detail": str(exc), "code": "invoice_paid"}, status=status.HTTP_409_CONFLICT)
        except client_updates.NoRecipientsError as exc:
            return Response({"detail": str(exc), "code": "no_recipients"}, status=status.HTTP_400_BAD_REQUEST)
        except MissingAdvocateNameError as exc:
            return Response({"detail": str(exc), "code": "missing_advocate_name"}, status=status.HTTP_400_BAD_REQUEST)
        except MissingContactEmailError as exc:
            return Response({"detail": str(exc), "code": "missing_contact_email"}, status=status.HTTP_400_BAD_REQUEST)
        except (client_updates.ClientMessageError, DeliveryError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 -- mail provider failures
            logger.exception("Client message %s send failed", message.id)
            return Response(
                {"detail": f"Could not send the message: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        message.refresh_from_db()
        payload = dict(result)
        payload["message"] = self.get_serializer(message).data
        return Response(payload, status=status.HTTP_200_OK)


class SentMessageListView(OwnerScopedMixin, generics.ListAPIView):
    """GET /api/sent-messages/?case_id=1&kind=invoice -- the audit log,
    newest first, at most MAX_LIST rows. Read-only by construction."""

    serializer_class = SentMessageSerializer

    def get_base_queryset(self):
        qs = SentMessage.objects.select_related("case", "sent_by")
        params = self.request.query_params
        if params.get("case_id"):
            qs = qs.filter(case_id=params["case_id"])
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        return qs

    def list(self, request, *args, **kwargs):
        rows = self.get_queryset()[:MAX_LIST]
        return Response(self.get_serializer(rows, many=True).data)
