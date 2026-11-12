from django.conf import settings
from django.db import models
from django.db.models import Q

from .mixins import OwnedModel


class AssistantDraft(OwnedModel):
    """One drafting request on one case: a status memo or a personal note.

    The model only ever proposes the body of a revision. Owner, case,
    approval and outputs are decided by server code. A draft never changes
    case: a different case is a new draft.
    """

    KIND_DOCUMENT = "document"
    KIND_NOTE = "note"
    KIND_CHOICES = [(KIND_DOCUMENT, "Document"), (KIND_NOTE, "Note")]

    SUBTYPE_STATUS_MEMO = "status_memo"
    SUBTYPE_PERSONAL_NOTE = "personal_note"
    SUBTYPE_CHOICES = [
        (SUBTYPE_STATUS_MEMO, "Case status memo"),
        (SUBTYPE_PERSONAL_NOTE, "Personal note"),
    ]
    KIND_FOR_SUBTYPE = {
        SUBTYPE_STATUS_MEMO: KIND_DOCUMENT,
        SUBTYPE_PERSONAL_NOTE: KIND_NOTE,
    }

    STATUS_QUEUED = "queued"
    STATUS_GENERATING = "generating"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_GENERATING, "Generating"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]
    PENDING_STATUSES = (STATUS_QUEUED, STATUS_GENERATING)

    id = models.BigAutoField(primary_key=True)
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="assistant_drafts"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    subtype = models.CharField(max_length=30, choices=SUBTYPE_CHOICES)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED
    )
    # The advocate's request: {instructions, audience, tone, length,
    # source_document_ids}. Validated by the create serializer.
    brief = models.JSONField(default=dict)
    # Trace only. A draft never inherits a conversation as context.
    origin_conversation = models.ForeignKey(
        "core.Conversation", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="+",
    )
    origin_message = models.ForeignKey(
        "core.Message", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="+",
    )
    current_revision = models.ForeignKey(
        "core.AssistantDraftRevision", on_delete=models.SET_NULL,
        blank=True, null=True, related_name="+",
    )
    # Bumped on every (re)generation request. The worker commits a preview
    # only if the generation it started with is still the current one.
    generation = models.PositiveIntegerField(default=1)
    job = models.ForeignKey(
        "core.ProcessingJob", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="+",
    )
    # A short fixed message for the UI. Never raw provider or exception text.
    error = models.CharField(max_length=255, blank=True, default="")
    client_request_id = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assistant_drafts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["owner", "case", "-created_at"],
                name="asst_draft_owner_case_idx",
            ),
            models.Index(fields=["owner", "status"], name="asst_draft_owner_status_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "client_request_id"],
                name="asst_draft_owner_request_uniq",
            ),
        ]

    def __str__(self):
        return f"Draft {self.id} [{self.subtype}/{self.status}] case={self.case_id}"


class AssistantDraftRevision(OwnedModel):
    """One immutable version of a draft body.

    A generated preview and every user edit is a new row. Only the three
    approval fields are ever written after creation, and only by
    core/services/drafting/approval.py through a queryset update.
    """

    SOURCE_GENERATED = "generated"
    SOURCE_EDITED = "edited"
    SOURCE_CHOICES = [(SOURCE_GENERATED, "Generated"), (SOURCE_EDITED, "Edited")]

    id = models.BigAutoField(primary_key=True)
    draft = models.ForeignKey(
        AssistantDraft, on_delete=models.CASCADE, related_name="revisions"
    )
    version = models.PositiveIntegerField()
    # Validated by core.services.drafting.schema.validate_body before save.
    body = models.JSONField()
    schema_version = models.PositiveSmallIntegerField(default=1)
    # What the server collected for this draft: a list of
    # {id, kind, label, ref, fingerprint}. `id` is the evidence ID a block
    # may cite. IDs and short labels only, never document text.
    evidence = models.JSONField(default=list, blank=True)
    missing_facts = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    approved_at = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, blank=True, null=True,
        related_name="+",
    )
    approved_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "assistant_draft_revisions"
        ordering = ["draft_id", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=["draft", "version"], name="asst_draft_rev_version_uniq"
            ),
            models.CheckConstraint(
                condition=(
                    Q(approved_at__isnull=True, approved_by__isnull=True, approved_hash="")
                    | (
                        Q(approved_at__isnull=False, approved_by__isnull=False)
                        & ~Q(approved_hash="")
                    )
                ),
                name="asst_draft_rev_approval_all_or_none",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("A draft revision is immutable. Create a new one.")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Draft {self.draft_id} v{self.version}"


class DraftOutput(OwnedModel):
    """What an approved revision was released as: a DOCX file or a saved
    case note. One row per (revision, destination), so a repeated click
    returns the same output."""

    DEST_DOCX = "docx"
    DEST_CASE_NOTE = "case_note"
    DESTINATION_CHOICES = [(DEST_DOCX, "DOCX export"), (DEST_CASE_NOTE, "Case note")]

    STATUS_PENDING = "pending"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.BigAutoField(primary_key=True)
    revision = models.ForeignKey(
        AssistantDraftRevision, on_delete=models.CASCADE, related_name="outputs"
    )
    destination = models.CharField(max_length=20, choices=DESTINATION_CHOICES)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    # Storage path relative to default_storage (same convention as
    # Document.file_path). Never returned by the API.
    file_path = models.CharField(max_length=500, blank=True, default="")
    filename = models.CharField(max_length=255, blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    case_note = models.ForeignKey(
        "core.CaseNote", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="+",
    )
    error = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assistant_draft_outputs"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["revision", "destination"],
                name="asst_draft_output_rev_dest_uniq",
            ),
        ]

    def __str__(self):
        return f"Output {self.id} [{self.destination}/{self.status}] rev={self.revision_id}"
