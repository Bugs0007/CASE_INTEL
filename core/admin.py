"""
Django admin configuration for all Case Intel models.
"""

from django.contrib import admin

from core.models import (
    ActivityLog,
    Case,
    CaseTag,
    CaseTagMap,
    Citation,
    Conversation,
    Document,
    DocumentChunk,
    DocumentTag,
    DocumentTagMap,
    DocumentVersion,
    Email,
    EmailAttachment,
    Folder,
    CourtFetchLog,
    CourtOrder,
    CourtTrackingPreview,
    GmailCredential,
    Hearing,
    Message,
    ProcessingJob,
    Task,
)


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = (
        "case_number", "title", "client_name", "case_type", "status", "priority",
        "tracking_enabled", "fetch_status", "cnr_number", "created_at",
    )
    list_filter = ("status", "case_type", "priority", "tracking_enabled", "fetch_status")
    search_fields = ("case_number", "title", "client_name", "opposing_party", "cnr_number")
    readonly_fields = ("created_at", "last_fetched_at")


@admin.register(CaseTag)
class CaseTagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(CaseTagMap)
class CaseTagMapAdmin(admin.ModelAdmin):
    list_display = ("case", "tag")
    list_filter = ("tag",)


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ("name", "parent_folder", "created_at")
    list_filter = ("parent_folder",)
    search_fields = ("name",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("filename", "case", "document_type", "processing_status", "chunk_count", "created_at")
    list_filter = ("processing_status", "document_type", "file_type")
    search_fields = ("filename",)
    readonly_fields = ("created_at",)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ("document", "version_number", "created_at")
    readonly_fields = ("created_at",)


@admin.register(DocumentTag)
class DocumentTagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(DocumentTagMap)
class DocumentTagMapAdmin(admin.ModelAdmin):
    list_display = ("document", "tag")
    list_filter = ("tag",)


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "job_type", "document", "case", "status", "progress_current",
        "progress_total", "attempts", "created_at", "started_at", "finished_at",
    )
    list_filter = ("status", "job_type")
    readonly_fields = ("created_at", "updated_at", "started_at", "finished_at")


@admin.register(CourtOrder)
class CourtOrderAdmin(admin.ModelAdmin):
    list_display = ("case", "order_number", "order_date", "source", "document", "created_at")
    list_filter = ("source", "case")
    readonly_fields = ("created_at",)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "created_at")
    list_filter = ("document",)
    readonly_fields = ("created_at",)


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "case", "sent_at", "has_attachments")
    list_filter = ("has_attachments", "case")
    search_fields = ("subject", "sender", "recipients")
    readonly_fields = ("created_at",)


@admin.register(EmailAttachment)
class EmailAttachmentAdmin(admin.ModelAdmin):
    list_display = ("filename", "email", "document", "created_at")
    readonly_fields = ("created_at",)


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "case", "started_at", "last_message_at")
    list_filter = ("case",)
    search_fields = ("title",)
    readonly_fields = ("started_at",)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "short_content", "created_at")
    list_filter = ("role",)
    readonly_fields = ("created_at",)

    @admin.display(description="Content")
    def short_content(self, obj: Message) -> str:
        return obj.content[:80] + "..." if len(obj.content) > 80 else obj.content


@admin.register(Citation)
class CitationAdmin(admin.ModelAdmin):
    list_display = ("message", "source_type", "document", "chunk", "created_at")
    list_filter = ("source_type",)
    readonly_fields = ("created_at",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "case", "status", "due_date", "created_at")
    list_filter = ("status",)
    search_fields = ("title", "description")
    readonly_fields = ("created_at",)


@admin.register(Hearing)
class HearingAdmin(admin.ModelAdmin):
    list_display = ("case", "hearing_type", "hearing_date", "source", "location", "judge", "status", "created_at")
    list_filter = ("status", "hearing_type", "source", "case")
    search_fields = ("location", "judge", "notes", "purpose")
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "hearing_date"


@admin.register(CourtFetchLog)
class CourtFetchLogAdmin(admin.ModelAdmin):
    list_display = ("case", "timestamp", "success", "duration_ms")
    list_filter = ("success", "case")
    readonly_fields = ("timestamp",)
    date_hierarchy = "timestamp"


@admin.register(CourtTrackingPreview)
class CourtTrackingPreviewAdmin(admin.ModelAdmin):
    list_display = ("token", "case", "user", "created_at", "expires_at")
    list_filter = ("case",)
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("activity_type", "case", "short_description", "created_at")
    list_filter = ("activity_type", "case")
    readonly_fields = ("created_at",)

    @admin.display(description="Description")
    def short_description(self, obj: ActivityLog) -> str:
        desc = obj.description or ""
        return desc[:80] + "..." if len(desc) > 80 else desc


@admin.register(GmailCredential)
class GmailCredentialAdmin(admin.ModelAdmin):
    list_display = ("email_address", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("email_address",)
    readonly_fields = ("created_at", "updated_at")
