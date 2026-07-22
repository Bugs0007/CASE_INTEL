from django.db import models

from .mixins import OwnedModel


class Task(OwnedModel):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True,
        related_name="tasks"
    )
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    due_date = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tasks"
        ordering = ["due_date"]

    def __str__(self):
        return self.title or f"Task {self.id}"
