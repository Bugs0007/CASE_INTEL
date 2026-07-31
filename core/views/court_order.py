"""
Court-order views -- list a case's orders (optionally for one hearing
date) and stream an individual order PDF.

Both are plain APIViews, so they scope to request.user by hand rather than
through OwnerScopedMixin (see the Multi-tenancy note in CLAUDE.md): a miss
is a 404, never a 403, so an id belonging to another advocate is
indistinguishable from one that doesn't exist.
"""

import logging
from datetime import date

from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, CourtOrder
from core.serializers import CourtOrderSerializer
from core.services.court_order_sync import order_sequence_sort_key

logger = logging.getLogger(__name__)


class CaseOrdersView(APIView):
    """Orders fetched from the court portal for one case.

    GET /api/cases/<id>/orders/                    -- every order
    GET /api/cases/<id>/orders/?date=2026-03-14    -- orders filed that day

    `date` is optional so the case-detail page can fetch a case's orders
    ONCE and bucket them by date across its hearing cards, instead of
    firing one request per hearing.

    A single date routinely carries several orders, so this always returns
    a list, sorted newest date first and by portal sequence within a date
    (order_number is free text -- see order_sequence_sort_key, which keeps
    "2" ahead of "10").

    Matching hearing date to order date needs no conversion: TIME_ZONE is
    UTC and court_tracking._upsert_hearings stores eCourts hearings at
    midnight UTC on the portal's date, so a Hearing's UTC date is exactly
    the CourtOrder.order_date it should line up with.
    """

    def get(self, request: Request, pk: int) -> Response:
        if not Case.objects.filter(id=pk, owner=request.user).exists():
            return Response(
                {"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND
            )

        orders = CourtOrder.objects.filter(
            case_id=pk, owner=request.user
        ).select_related("document")

        date_param = request.query_params.get("date")
        if date_param:
            try:
                target = date.fromisoformat(date_param)
            except ValueError:
                return Response(
                    {"detail": "Invalid 'date' -- expected YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            orders = orders.filter(order_date=target)

        # Sorted in Python: order_number is a CharField holding portal text,
        # so the DB's string ordering would file "10" before "2". Undated
        # orders sort last.
        ordered = sorted(
            orders,
            key=lambda o: (
                o.order_date is None,
                -(o.order_date.toordinal() if o.order_date else 0),
                order_sequence_sort_key(o.order_number),
            ),
        )
        return Response(CourtOrderSerializer(ordered, many=True).data)


class CourtOrderFileView(APIView):
    """Stream one order's PDF.

    GET /api/orders/<id>/file/

    Streams the bytes through this view rather than handing back a
    storage URL: on local disk /media/... is served with no auth at all,
    which would make every order readable by anyone holding (or guessing)
    the path. The cost is that S3-hosted orders transit the backend
    instead of going straight from the bucket -- deliberate, so ownership
    is checked on every single read. DocumentDownloadView keeps its
    presigned-URL behaviour for ordinary documents.

    Content-Disposition is inline, so the browser renders the PDF in the
    tab the frontend opened rather than downloading it.
    """

    def get(self, request: Request, pk: int) -> Response:
        try:
            order = CourtOrder.objects.select_related("document").get(
                id=pk, owner=request.user
            )
        except CourtOrder.DoesNotExist:
            return Response(
                {"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND
            )

        if order.document is None:
            return Response(
                {"detail": "This order has no file attached."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            handle = default_storage.open(order.document.file_path, "rb")
        except Exception as exc:
            # Only the local backend reliably raises FileNotFoundError for a
            # missing file; S3 surfaces a botocore ClientError instead. So
            # rather than matching on exception type, ask the storage
            # whether the file is there -- an extra round-trip, but only on
            # the error path, and it keeps "gone" a 404 on both backends.
            missing = False
            try:
                missing = not default_storage.exists(order.document.file_path)
            except Exception:  # noqa: BLE001 -- storage itself is unreachable
                pass
            if missing:
                logger.warning(
                    "Order %d references a missing file (%s).",
                    pk,
                    order.document.file_path,
                )
                return Response(
                    {"detail": "The order file is no longer available."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            logger.exception("Could not open the file for order %d", pk)
            return Response(
                {"detail": f"File is unavailable: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return FileResponse(
            handle,
            content_type="application/pdf",
            as_attachment=False,
            filename=order.document.filename,
        )
