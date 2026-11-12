from django.db import models

from .mixins import OwnedModel


class Conversation(OwnedModel):
    # What a conversation is about. `case` is a Case Bot chat on one case,
    # `legacy_documents` the older all-documents chat with no case, and
    # `practice` a practice-assistant chat. The old /api/chat/ endpoint never
    # continues a `practice` conversation.
    SCOPE_CASE = "case"
    SCOPE_LEGACY_DOCUMENTS = "legacy_documents"
    SCOPE_PRACTICE = "practice"
    SCOPE_CHOICES = [
        (SCOPE_CASE, "Case"),
        (SCOPE_LEGACY_DOCUMENTS, "Legacy documents"),
        (SCOPE_PRACTICE, "Practice"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True,
        related_name="conversations"
    )
    # Left blank by callers that predate scopes: save() derives it from
    # `case`. A row that still reaches the database blank (bulk_create, raw
    # SQL) is refused by the check constraint below.
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, blank=True)
    title = models.CharField(max_length=500, blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "conversations"
        ordering = ["-last_message_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="case", case__isnull=False)
                    | models.Q(
                        scope__in=["legacy_documents", "practice"],
                        case__isnull=True,
                    )
                ),
                name="conversations_scope_matches_case_chk",
            ),
        ]

    def __str__(self):
        return self.title or f"Conversation {self.id}"

    def save(self, *args, **kwargs):
        if not self.scope:
            self.scope = (
                self.SCOPE_CASE if self.case_id else self.SCOPE_LEGACY_DOCUMENTS
            )
        super().save(*args, **kwargs)
