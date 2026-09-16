from django.db import models
from django.db.models import Q

from .mixins import OwnedModel


class Task(OwnedModel):
    """Anything with a due date on a case -- the ONE deadline surface.

    An advocate's own to-do, a direction from a court order ("file counter
    within 4 weeks"), and a limitation deadline ("appeal by 12 Oct") are all
    Tasks, distinguished by `kind`. Keeping them in one table means "what is
    due / overdue" is answered by one query and one UI list, not a merge of
    several.

    System-generated tasks (any kind other than manual) are written only
    through core.services.tasks.upsert_system_task, keyed by `dedup_key` so
    regeneration is idempotent. Once the advocate edits one (`user_modified`),
    regeneration never touches it again -- the same rule party-role detection
    follows for a role the advocate has set by hand.
    """

    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    OPEN_STATUSES = (STATUS_PENDING, STATUS_IN_PROGRESS)

    KIND_MANUAL = "manual"
    KIND_ORDER_DIRECTION = "order_direction"
    KIND_LIMITATION = "limitation"

    KIND_CHOICES = [
        (KIND_MANUAL, "Added by you"),
        (KIND_ORDER_DIRECTION, "Court order direction"),
        (KIND_LIMITATION, "Limitation deadline"),
    ]

    # How a system-generated due date was arrived at, so the UI can say so
    # plainly instead of presenting every date with the same confidence.
    # Blank for dates the advocate typed in.
    BASIS_EXPLICIT_DATE = "explicit_date"
    BASIS_RELATIVE_TO_ORDER = "relative_to_order"
    BASIS_NEXT_HEARING_FALLBACK = "next_hearing_fallback"
    BASIS_LIMITATION_RULE = "limitation_rule"

    DUE_DATE_BASIS_CHOICES = [
        (BASIS_EXPLICIT_DATE, "Date stated in the order"),
        (BASIS_RELATIVE_TO_ORDER, "Counted from the order date"),
        (BASIS_NEXT_HEARING_FALLBACK, "No period stated -- next hearing date"),
        (BASIS_LIMITATION_RULE, "Computed from a limitation rule"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True,
        related_name="tasks"
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_MANUAL)
    # A calendar date, not a datetime: legal deadlines fall on a day, and a
    # midnight-UTC datetime renders as the previous day in some clients.
    due_date = models.DateField(blank=True, null=True)
    due_date_basis = models.CharField(
        max_length=30, choices=DUE_DATE_BASIS_CHOICES, blank=True, default=""
    )

    # --- Provenance for system-generated tasks ---
    source_order = models.ForeignKey(
        "core.CourtOrder",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="tasks",
    )
    # The direction text or rule label the task came from. Kept on the row
    # so the task still explains itself if the order is later deleted.
    source_text = models.TextField(blank=True, default="")
    rule_key = models.CharField(max_length=60, blank=True, default="")
    trigger_date = models.DateField(blank=True, null=True)
    # Suggested by the system and not yet confirmed by the advocate.
    needs_review = models.BooleanField(default=False)
    user_modified = models.BooleanField(default=False)
    # Stable identity for a system-generated task, unique per owner. Blank
    # for manual tasks.
    dedup_key = models.CharField(max_length=120, blank=True, default="")

    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tasks"
        ordering = ["due_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "dedup_key"],
                condition=~Q(dedup_key=""),
                name="unique_task_owner_dedup_key",
            )
        ]
        indexes = [
            models.Index(fields=["owner", "status", "due_date"], name="tasks_owner_status_due_idx"),
        ]

    @property
    def is_system_generated(self) -> bool:
        return self.kind != self.KIND_MANUAL

    def __str__(self):
        return self.title or f"Task {self.id}"
