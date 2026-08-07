"""
Serializers for legal cases.
"""

from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import serializers

from core.models import AppearanceFee, Case

from .client_contact import ClientContactSerializer


class CaseSerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()
    hearing_count = serializers.SerializerMethodField()
    thread_count = serializers.IntegerField(read_only=True, default=0)
    conversation_count = serializers.IntegerField(read_only=True, default=0)
    needs_attention = serializers.SerializerMethodField()
    next_hearing_date = serializers.SerializerMethodField()
    client_contacts = ClientContactSerializer(many=True, read_only=True)
    fee_summary = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            "id",
            "case_number",
            "title",
            "client_name",
            "client_contacts",
            "opposing_party",
            "user_party_role",
            "case_type",
            "status",
            "priority",
            "filing_date",
            "notes",
            "created_at",
            "document_count",
            "hearing_count",
            "thread_count",
            "conversation_count",
            "cnr_number",
            "court_type",
            "tracking_config",
            "tracking_enabled",
            "fetch_status",
            "last_fetched_at",
            "party_advocate_data",
            "needs_attention",
            "next_hearing_date",
            "fee_summary",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "cnr_number",
            "fetch_status",
            "last_fetched_at",
            "party_advocate_data",
        ]

    def get_document_count(self, obj: Case) -> int:
        return obj.documents.count()

    def get_hearing_count(self, obj: Case) -> int:
        return obj.hearings.count()

    def get_next_hearing_date(self, obj: Case):
        # Populated via queryset annotation (see core/views/case.py) when
        # available; falls back to a direct query otherwise (e.g. CaseDetailView).
        if hasattr(obj, "_next_hearing_date"):
            return obj._next_hearing_date
        hearing = (
            obj.hearings.filter(status="scheduled", hearing_date__gte=timezone.now())
            .order_by("hearing_date")
            .first()
        )
        return hearing.hearing_date if hearing else None

    def get_fee_summary(self, obj: Case) -> dict:
        """Pending/invoiced/paid totals for the case page's fee summary.

        "Outstanding" is pending + invoiced -- both are money not yet
        received, which is the number an advocate actually wants at a
        glance; keeping the two components alongside it means the UI can
        still distinguish "not billed yet" from "billed, awaiting
        payment".

        One aggregate query per case. That is fine for the case DETAIL
        page (a single case), which is where this is rendered; a future
        list view that wants these totals should annotate the queryset
        rather than relying on this per-row.
        """
        rows = (
            AppearanceFee.objects.filter(hearing__case=obj)
            .values("status")
            .annotate(total=Sum("amount"), count=Count("id"))
        )
        totals = {
            AppearanceFee.STATUS_PENDING: (Decimal("0.00"), 0),
            AppearanceFee.STATUS_INVOICED: (Decimal("0.00"), 0),
            AppearanceFee.STATUS_PAID: (Decimal("0.00"), 0),
        }
        for row in rows:
            totals[row["status"]] = (row["total"] or Decimal("0.00"), row["count"])

        pending_amount, pending_count = totals[AppearanceFee.STATUS_PENDING]
        invoiced_amount, invoiced_count = totals[AppearanceFee.STATUS_INVOICED]
        paid_amount, paid_count = totals[AppearanceFee.STATUS_PAID]

        return {
            "pending_amount": str(pending_amount),
            "pending_count": pending_count,
            "invoiced_amount": str(invoiced_amount),
            "invoiced_count": invoiced_count,
            "paid_amount": str(paid_amount),
            "paid_count": paid_count,
            "outstanding_amount": str(pending_amount + invoiced_amount),
            "total_amount": str(pending_amount + invoiced_amount + paid_amount),
        }

    def get_needs_attention(self, obj: Case) -> bool:
        # Populated via queryset annotation (see core/views/case.py); defaults
        # to False when the annotations aren't present (e.g. CaseDetailView).
        return bool(
            getattr(obj, "has_upcoming_hearing", False)
            or getattr(obj, "has_ecourts_update", False)
            or getattr(obj, "has_failed_document", False)
        )
