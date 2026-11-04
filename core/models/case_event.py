from django.db import models
from django.db.models import F, Q

from .mixins import OwnedModel


class CaseEvent(OwnedModel):
    """An appointment the advocate puts on a case's calendar: an arbitration
    sitting, a mediation, a client meeting or call, a site visit.

    Deliberately NOT a Hearing (the cause-list service, fees/invoicing and
    eCourts sync all treat every scheduled Hearing as a court date) and NOT
    a Task (a Task is a due date, not an appointment with a time).

    `date` is the India calendar date and `start_time`/`end_time` are India
    local times -- the same reasoning as Task.due_date: these are things a
    person plans on a day, so they are stored as that day, not as a UTC
    instant that renders as the neighbouring day in some clients. A null
    `start_time` means all-day.
    """

    TYPE_ARBITRATION = "arbitration"
    TYPE_MEDIATION = "mediation"
    TYPE_CLIENT_MEETING = "client_meeting"
    TYPE_CLIENT_CALL = "client_call"
    TYPE_INTERNAL_MEETING = "internal_meeting"
    TYPE_SITE_VISIT = "site_visit"
    TYPE_FILING = "filing"
    TYPE_OTHER = "other"

    EVENT_TYPE_CHOICES = [
        (TYPE_ARBITRATION, "Arbitration"),
        (TYPE_MEDIATION, "Mediation"),
        (TYPE_CLIENT_MEETING, "Client meeting"),
        (TYPE_CLIENT_CALL, "Client call"),
        (TYPE_INTERNAL_MEETING, "Internal meeting"),
        (TYPE_SITE_VISIT, "Site visit"),
        (TYPE_FILING, "Filing"),
        (TYPE_OTHER, "Other"),
    ]

    STATUS_SCHEDULED = "scheduled"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="events"
    )
    title = models.CharField(max_length=200)
    event_type = models.CharField(
        max_length=20, choices=EVENT_TYPE_CHOICES, default=TYPE_OTHER
    )
    date = models.DateField()
    start_time = models.TimeField(blank=True, null=True)
    end_time = models.TimeField(blank=True, null=True)
    location = models.CharField(
        max_length=255, blank=True, default="",
        help_text="An address or a meeting link.",
    )
    notes = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_SCHEDULED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "case_events"
        ordering = ["date", "start_time"]
        indexes = [
            models.Index(fields=["owner", "date"], name="case_events_owner_date_idx"),
        ]
        constraints = [
            # The serializer gives the friendly message; this is the backstop
            # for rows written any other way (admin, shell).
            models.CheckConstraint(
                condition=Q(end_time__isnull=True)
                | (Q(start_time__isnull=False) & Q(end_time__gt=F("start_time"))),
                name="case_event_end_after_start",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.date})"
