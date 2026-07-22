from django.db import models

from .mixins import OwnedModel


class ProcessingJob(OwnedModel):
    """A queued unit of document-processing work, claimed by the
    `process_jobs` worker via select_for_update(skip_locked=True).

    DB-backed on purpose: this project deliberately runs without
    Redis/Celery (see the Celery section in settings.py), so Postgres row
    locking is the queue. `updated_at` doubles as the worker heartbeat --
    a job stuck in "running" whose heartbeat has gone stale is reclaimed
    by the worker loop (crashed worker), so nothing stays "running"
    forever.
    """

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
    ]

    JOB_TYPE_CHOICES = [
        ("document", "Document Processing"),
        ("order_sync", "Court Order Sync"),
    ]

    # Explicit pk so this model doesn't add to the pre-existing W042
    # (auto-created AutoField) warning noise from the other models.
    id = models.BigAutoField(primary_key=True)

    # "document" jobs process one Document (document set, case unused).
    # "order_sync" jobs fetch order PDFs from the court portal for one
    # tracked Case (case set, document null) and enqueue a document job
    # per downloaded file -- reusing this same queue/worker rather than a
    # parallel pipeline.
    job_type = models.CharField(
        max_length=20, choices=JOB_TYPE_CHOICES, default="document"
    )
    document = models.ForeignKey(
        "core.Document",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="processing_jobs",
    )
    case = models.ForeignKey(
        "core.Case",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="processing_jobs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued")
    progress_current = models.IntegerField(default=0)
    progress_total = models.IntegerField(default=0)
    error = models.TextField(blank=True, default="")
    # How many times this job has been claimed. Guards against a crash
    # loop: a job that keeps killing the worker is failed permanently
    # after MAX_ATTEMPTS (see process_jobs) instead of requeueing forever.
    attempts = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "processing_jobs"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        target = f"doc={self.document_id}" if self.document_id else f"case={self.case_id}"
        return f"Job {self.id} [{self.job_type}/{self.status}] {target}"

    @classmethod
    def enqueue(cls, document) -> tuple["ProcessingJob", bool]:
        """Enqueue processing for a document, deduplicating active jobs.

        Returns (job, created). If a queued/running job already exists for
        this document, that job is returned instead of creating a second.
        """
        existing = (
            cls.objects
            .filter(document=document, status__in=["queued", "running"])
            .order_by("created_at")
            .first()
        )
        if existing is not None:
            return existing, False
        return cls.objects.create(owner=document.owner, document=document), True

    @classmethod
    def enqueue_order_sync(cls, case) -> tuple["ProcessingJob", bool]:
        """Enqueue a court-order sync for a tracked case, deduplicating
        active jobs the same way enqueue() does for documents."""
        existing = (
            cls.objects
            .filter(case=case, job_type="order_sync", status__in=["queued", "running"])
            .order_by("created_at")
            .first()
        )
        if existing is not None:
            return existing, False
        return cls.objects.create(owner=case.owner, case=case, job_type="order_sync"), True
