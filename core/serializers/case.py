"""
Serializers for legal cases.
"""

from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import serializers

from core.models import AppearanceFee, Case

from .client import ClientSummarySerializer, scope_client_field
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
    client_detail = ClientSummarySerializer(source="client", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        scope_client_field(self, self.context.get("request"))

    class Meta:
        model = Case
        fields = [
            "id",
            "case_number",
            "case_number_raw",
            "title",
            "client_name",
            "client",
            "client_detail",
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
            "case_number_raw",
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


class CaseDetailSerializer(CaseSerializer):
    """The case page's shape: everything in CaseSerializer, plus what only
    the detail page needs -- each costs a query or two, which is fine for
    one case and would be an N+1 on the list.

      tracking_snapshot   what the latest successful eCourts fetch said
                          (status, stage, judge, court, nature of disposal)
      tracking_freshness  whether that is still current (court_tracking.
                          tracking_freshness) and when Refresh unlocks
      disposal            the case looks disposed of (disposal.py): the
                          page offers to close it, never closes it itself
      update_recipient_count
                          contacts who can receive case-update emails; 0
                          means no drafts will be written for this case
      petitioner_name / respondent_name
                          the parties as the court record gives them
      parties             petitioner/respondent from the record, else the
                          "X vs Y" title, plus which is ours/opposing
                          (core/services/parties.py -- the same answer the
                          document generator prints)
    """

    tracking_snapshot = serializers.SerializerMethodField()
    tracking_freshness = serializers.SerializerMethodField()
    disposal = serializers.SerializerMethodField()
    update_recipient_count = serializers.SerializerMethodField()
    parties = serializers.SerializerMethodField()

    class Meta(CaseSerializer.Meta):
        fields = CaseSerializer.Meta.fields + [
            "petitioner_name",
            "respondent_name",
            "tracking_snapshot",
            "tracking_freshness",
            "disposal",
            "update_recipient_count",
            "parties",
        ]
        read_only_fields = CaseSerializer.Meta.read_only_fields + ["petitioner_name", "respondent_name"]

    def _snapshot(self, obj: Case):
        if not hasattr(obj, "_tracking_snapshot"):
            from core.services.court_tracking import latest_snapshot

            obj._tracking_snapshot = latest_snapshot(obj) if obj.tracking_enabled else None
        return obj._tracking_snapshot

    def get_tracking_snapshot(self, obj: Case):
        snapshot = self._snapshot(obj)
        if not snapshot:
            return None
        keys = ("case_status", "case_stage", "court_and_judge", "court_name", "nature_of_disposal", "next_hearing_date")
        return {key: snapshot.get(key) for key in keys}

    def get_tracking_freshness(self, obj: Case):
        from core.services.court_tracking import tracking_freshness

        return tracking_freshness(obj)

    def get_disposal(self, obj: Case):
        from core.services.disposal import case_disposal

        disposal = case_disposal(obj, snapshot=self._snapshot(obj) or {})
        return disposal.as_dict() if disposal else None

    def get_parties(self, obj: Case) -> dict:
        from core.services.parties import case_parties

        return case_parties(obj).as_dict()

    def get_update_recipient_count(self, obj: Case) -> int:
        from core.services.client_updates.service import update_recipients

        return len(update_recipients(obj))


class CaseCreateSerializer(serializers.ModelSerializer):
    """Validates manual case entry: POST /api/cases/.

    The alternative to the advocate-search/import flow (core/services/
    advocate_import.py) -- for a case that search doesn't turn up, or when
    the advocate would rather just type it in. Deliberately narrow: no
    cnr_number/court_type/tracking_config/tracking_enabled/fetch_status/
    party_advocate_data fields here at all, since those are only ever set
    through the court-tracking preview/confirm flow (core/services/
    court_tracking.py), which works identically regardless of how the case
    was created -- a manually-created case can be linked to a CNR
    afterwards exactly the same way an imported one can.

    client_name is left optional (default "") rather than required: the
    richer ClientContact model (name/email/phone/role/billing flag) is
    the actual source of truth for client info now, added via the case
    detail page's "Edit Details" dialog right after creation -- same
    two-step flow an advocate-search import already uses.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        scope_client_field(self, self.context.get("request"))

    class Meta:
        model = Case
        fields = [
            "case_number",
            "title",
            "client_name",
            "client",
            "opposing_party",
            "user_party_role",
            "case_type",
            "status",
            "priority",
            "filing_date",
            "notes",
        ]
        extra_kwargs = {
            "client_name": {"required": False, "allow_blank": True, "default": ""},
            "opposing_party": {"required": False, "allow_blank": True, "allow_null": True},
            "notes": {"required": False, "allow_blank": True, "allow_null": True},
        }


class CaseCnrCreateSerializer(CaseCreateSerializer):
    """Same field set/validation as CaseCreateSerializer, for the confirm
    step of the "Track by CNR" quick-add flow (core/views/case_tracking.py's
    CaseCnrCreateView).

    Kept as a distinct name for that call site rather than reusing
    CaseCreateSerializer directly, even though the field set is currently
    identical: a case_number collision here needs to reach
    create_case_from_cnr_preview()'s IntegrityError handling (core/
    services/court_tracking.py) so it can tell a same-user CNR duplicate
    (DuplicateCnrError, a link to the existing case) apart from a
    same-user case_number duplicate (DuplicateCaseNumberError) -- see that
    function's docstring. No UniqueValidator to strip here: case_number
    is no longer `unique=True` on the model (see the (owner, case_number)
    UniqueConstraint), and DRF can't auto-generate a validator for that
    constraint since `owner` isn't a field on this serializer.
    """
