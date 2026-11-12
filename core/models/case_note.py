from django.db import models

from .mixins import OwnedModel


class CaseNote(OwnedModel):
    """A note the advocate keeps on a case. Separate from Case.notes (one
    free-text field): these are individual rows, listed under the case.

    A note saved from an approved draft keeps a link to that exact revision.
    The link is unique, so saving the same revision twice gives one note, and
    it is SET_NULL, so the note outlives its draft.
    """

    id = models.BigAutoField(primary_key=True)
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="case_notes"
    )
    title = models.CharField(max_length=200)
    body = models.TextField()  # plain text
    origin_revision = models.OneToOneField(
        "core.AssistantDraftRevision", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="saved_note",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "case_notes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["owner", "case", "-created_at"],
                name="case_notes_owner_case_idx",
            ),
        ]

    def __str__(self):
        return f"{self.title} (case {self.case_id})"
