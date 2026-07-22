from django.db import models

from .mixins import OwnedModel


class Citation(OwnedModel):
    SOURCE_TYPE_CHOICES = [
        ("document", "Document"),
        ("email", "Email"),
        ("chunk", "Chunk"),
    ]

    message = models.ForeignKey(
        "core.Message", on_delete=models.CASCADE, related_name="citations"
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    document = models.ForeignKey(
        "core.Document", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="citations"
    )
    email = models.ForeignKey(
        "core.Email", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="citations"
    )
    chunk = models.ForeignKey(
        "core.DocumentChunk", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="citations"
    )
    citation_text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "citations"

    def __str__(self):
        return f"Citation ({self.source_type}) for message {self.message_id}"
