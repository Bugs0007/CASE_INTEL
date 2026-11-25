from django.db import models

from .mixins import OwnedModel


class McpProposal(OwnedModel):
    """A change Claude proposed through the MCP connector, waiting for the
    user to confirm it (docs/MCP_PLAN.md section 5, "propose, then confirm").

    A propose_* tool writes only this row -- never case data. Only
    confirm_proposal runs the real change, once, after checking owner,
    status, expiry and that `args` still hash to `args_hash`; `result` keeps
    what it created so a second confirm returns the same answer.
    """

    STATUS_OPEN = "open"
    STATUS_CONFIRMED = "confirmed"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    id = models.BigAutoField(primary_key=True)
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, null=True, blank=True, related_name="mcp_proposals"
    )
    tool = models.CharField(max_length=50)
    args = models.JSONField(default=dict)
    args_hash = models.CharField(max_length=64)
    # Plain text built by server code from `args`, shown to the user.
    preview = models.TextField()
    blockers = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    client_id = models.CharField(max_length=255, blank=True, default="")
    token_id = models.BigIntegerField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mcp_proposals"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "status"], name="mcp_proposals_owner_status_idx")]

    def __str__(self):
        return f"McpProposal #{self.pk} {self.tool} ({self.status})"
