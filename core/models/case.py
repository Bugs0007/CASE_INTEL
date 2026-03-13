from django.db import models


class Case(models.Model):
    CASE_TYPE_CHOICES = [
        ("civil", "Civil"),
        ("criminal", "Criminal"),
        ("family", "Family"),
        ("corporate", "Corporate"),
        ("ip", "Intellectual Property"),
        ("labor", "Labor"),
        ("tax", "Tax"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
        ("pending", "Pending"),
        ("archived", "Archived"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    case_number = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=500)
    client_name = models.CharField(max_length=255)
    opposing_party = models.CharField(max_length=255, blank=True, null=True)
    case_type = models.CharField(max_length=50, choices=CASE_TYPE_CHOICES, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    filing_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cases"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.case_number} - {self.title}"
