"""Appearance-fee views: CRUD plus the three lifecycle actions
(generate invoice / send to billing contact / mark paid) and the invoice
PDF stream.

The action endpoints are plain APIViews and scope to request.user by
hand (see the Multi-tenancy note in CLAUDE.md) -- a miss is a 404, never
a 403, so a fee id belonging to another advocate is indistinguishable
from one that doesn't exist. None of them mutate status directly; they
all delegate to core/services/invoice_service.py, which owns the
transition rules.
"""

import logging

from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AppearanceFee
from core.serializers import AppearanceFeeSerializer
from core.services import invoice_service
from core.views.mixins import OwnerScopedMixin

logger = logging.getLogger(__name__)


def _get_own_fee(request: Request, pk: int) -> AppearanceFee | None:
    return (
        AppearanceFee.objects.select_related("hearing__case")
        .filter(id=pk, owner=request.user)
        .first()
    )


class AppearanceFeeListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """List or create appearance fees.

    GET  /api/appearance-fees/
    GET  /api/appearance-fees/?case_id=1
    GET  /api/appearance-fees/?hearing_id=2
    GET  /api/appearance-fees/?status=pending
    POST /api/appearance-fees/

    Scoped to request.user (OwnerScopedMixin) -- as with Hearing, a
    case_id belonging to another user still yields an empty queryset,
    since no fee owned by request.user can carry another user's case.
    """

    serializer_class = AppearanceFeeSerializer

    def get_base_queryset(self):
        qs = AppearanceFee.objects.select_related("hearing__case")
        case_id = self.request.query_params.get("case_id")
        if case_id:
            qs = qs.filter(hearing__case_id=case_id)
        hearing_id = self.request.query_params.get("hearing_id")
        if hearing_id:
            qs = qs.filter(hearing_id=hearing_id)
        fee_status = self.request.query_params.get("status")
        if fee_status:
            qs = qs.filter(status=fee_status)
        return qs

    def perform_create(self, serializer):
        # Default the amount to the advocate's configured default fee
        # when the client didn't send one -- that's what the profile
        # field is for.
        if not serializer.validated_data.get("amount"):
            profile = invoice_service.get_or_create_profile(self.request.user)
            serializer.validated_data["amount"] = profile.default_fee_amount
        serializer.save(owner=self.request.user)


class AppearanceFeeDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete an appearance fee.

    GET    /api/appearance-fees/<id>/
    PATCH  /api/appearance-fees/<id>/   (amount/notes only -- see serializer)
    DELETE /api/appearance-fees/<id>/

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = AppearanceFeeSerializer
    queryset = AppearanceFee.objects.select_related("hearing__case")


class AppearanceFeeInvoiceView(APIView):
    """Generate (or re-render) this fee's invoice PDF; status -> INVOICED.

    POST /api/appearance-fees/<id>/invoice/
    """

    def post(self, request: Request, pk: int) -> Response:
        fee = _get_own_fee(request, pk)
        if fee is None:
            return Response(
                {"detail": "Appearance fee not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            fee = invoice_service.generate_invoice(fee)
        except invoice_service.InvoiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 -- PDF/storage failures
            logger.exception("Invoice generation failed for fee %d", pk)
            return Response(
                {"detail": f"Could not generate the invoice: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(AppearanceFeeSerializer(fee).data, status=status.HTTP_200_OK)


class AppearanceFeeInvoiceFileView(APIView):
    """Stream the generated invoice PDF.

    GET /api/appearance-fees/<id>/invoice/file/

    Streamed through this view rather than handed back as a storage URL,
    for the same reason as CourtOrderFileView: on local disk /media/...
    is served with no auth at all, and an invoice carries the client's
    name and the amount billed.
    """

    def get(self, request: Request, pk: int) -> Response:
        fee = _get_own_fee(request, pk)
        if fee is None:
            return Response(
                {"detail": "Appearance fee not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if not fee.invoice_pdf_path:
            return Response(
                {"detail": "No invoice has been generated for this fee yet."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            handle = default_storage.open(fee.invoice_pdf_path, "rb")
        except Exception as exc:  # noqa: BLE001
            # Same both-backends treatment as CourtOrderFileView: only the
            # local backend reliably raises FileNotFoundError, so ask the
            # storage whether the file is actually there.
            missing = False
            try:
                missing = not default_storage.exists(fee.invoice_pdf_path)
            except Exception:  # noqa: BLE001 -- storage itself is unreachable
                pass
            if missing:
                logger.warning(
                    "Fee %d references a missing invoice file (%s).", pk, fee.invoice_pdf_path
                )
                return Response(
                    {"detail": "The invoice file is no longer available. Generate it again."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            logger.exception("Could not open the invoice file for fee %d", pk)
            return Response(
                {"detail": f"File is unavailable: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return FileResponse(
            handle,
            content_type="application/pdf",
            as_attachment=False,
            filename=f"{fee.invoice_number or 'invoice'}.pdf",
        )


class AppearanceFeeSendView(APIView):
    """Email the invoice to the case's billing contact.

    POST /api/appearance-fees/<id>/send/

    Returns 200 with sent=false (not an error) when SMTP isn't
    configured -- the invoice is logged instead, and the response names
    the env vars needed to enable real delivery.
    """

    def post(self, request: Request, pk: int) -> Response:
        fee = _get_own_fee(request, pk)
        if fee is None:
            return Response(
                {"detail": "Appearance fee not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            result = invoice_service.send_invoice(fee)
        except invoice_service.InvoiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 -- SMTP/storage failures
            logger.exception("Invoice send failed for fee %d", pk)
            return Response(
                {"detail": f"Could not send the invoice: {exc}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        fee.refresh_from_db()
        payload = dict(result)
        payload["fee"] = AppearanceFeeSerializer(fee).data
        return Response(payload, status=status.HTTP_200_OK)


class AppearanceFeeMarkPaidView(APIView):
    """Mark an invoiced fee as paid.

    POST /api/appearance-fees/<id>/mark-paid/
    """

    def post(self, request: Request, pk: int) -> Response:
        fee = _get_own_fee(request, pk)
        if fee is None:
            return Response(
                {"detail": "Appearance fee not found."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            fee = invoice_service.mark_paid(fee)
        except invoice_service.InvalidFeeTransitionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(AppearanceFeeSerializer(fee).data, status=status.HTTP_200_OK)
