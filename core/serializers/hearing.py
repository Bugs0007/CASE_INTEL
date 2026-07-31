"""
Serializers for case hearings.
"""

from rest_framework import serializers

from core.models import Case, Hearing

from .appearance_fee import NestedAppearanceFeeSerializer
from .order_summary import build_order_summary
from .travel_booking import NestedTravelBookingSerializer


class HearingSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source="case.title", read_only=True)
    hearing_type_display = serializers.CharField(
        source="get_hearing_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    # Embedded read-only so the hearing card can render its fee badge and
    # booking state without a second round-trip per hearing. appearance_fee
    # is a OneToOne, so it's null on hearings with no fee recorded yet.
    appearance_fee = NestedAppearanceFeeSerializer(read_only=True)
    travel_bookings = NestedTravelBookingSerializer(many=True, read_only=True)
    cause_list_status_display = serializers.CharField(
        source="get_cause_list_status_display", read_only=True
    )
    order_summary = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the writable "case" field to the requesting user's own
        # cases -- without this, any case pk (including another user's)
        # would pass field-level validation and let a hearing be attached
        # to a case that isn't the caller's.
        request = self.context.get("request")
        if request is not None and "case" in self.fields:
            self.fields["case"].queryset = Case.objects.filter(owner=request.user)

    def get_order_summary(self, obj):
        """The Order Overview for the order filed on THIS hearing's date,
        so the calendar entry can show what happened without a second
        request per hearing. None when no order was filed that day.

        Reads from `case.court_orders` and filters in Python rather than
        querying per hearing: the hearing views prefetch that relation
        (see core/views/hearing.py), so a calendar of 60 hearings costs
        one extra query in total, not 60.

        Date matching needs no conversion -- TIME_ZONE is UTC and eCourts
        hearings are stored at midnight UTC on the portal's date, so a
        hearing's UTC date is exactly the CourtOrder.order_date to match
        (same reasoning as CaseOrdersView).
        """
        if obj.case_id is None:
            return None

        hearing_day = obj.hearing_date.date()
        match = next(
            (
                order
                for order in obj.case.court_orders.all()
                if order.order_date == hearing_day
                and order.summary_status != "pending"
            ),
            None,
        )
        return build_order_summary(match) if match is not None else None

    class Meta:
        model = Hearing
        fields = [
            "id",
            "case",
            "case_title",
            "hearing_date",
            "hearing_type",
            "hearing_type_display",
            "location",
            "judge",
            "status",
            "status_display",
            "notes",
            "outcome",
            "source",
            "business_date",
            "purpose",
            "appearance_fee",
            "travel_bookings",
            "cause_list_status",
            "cause_list_status_display",
            "cause_list_item_number",
            "cause_list_court_hall",
            "cause_list_stage",
            "cause_list_checked_at",
            "order_summary",
            "created_at",
            "updated_at",
        ]
        # The cause-list fields are written only by the fetch job
        # (manage.py fetch_cause_lists), never by an API client -- an
        # advocate editing their own item number would make the field
        # meaningless.
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "cause_list_status",
            "cause_list_item_number",
            "cause_list_court_hall",
            "cause_list_stage",
            "cause_list_checked_at",
        ]
