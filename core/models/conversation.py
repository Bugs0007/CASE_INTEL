from django.db import models


class Conversation(models.Model):
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True,
        related_name="conversations"
    )
    title = models.CharField(max_length=500, blank=True, null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "conversations"
        ordering = ["-last_message_at"]

    def __str__(self):
        return self.title or f"Conversation {self.id}"
