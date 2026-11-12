from django.db import models

from .mixins import OwnedModel


class Message(OwnedModel):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
        ("system", "System"),
    ]

    conversation = models.ForeignKey(
        "core.Conversation", on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    # Typed pointers to owned records a practice answer rests on; each item
    # has the shape of `Reference` in core/services/practice_assistant/contracts.py.
    references = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
