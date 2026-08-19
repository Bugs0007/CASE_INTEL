from django.db import models
from django.utils import timezone

from .mixins import OwnedModel


class JobAlreadyRunningError(Exception):
    """Raised when a system-wide-singleton job type (advocate_search /
    advocate_import) is enqueued while one is already queued or running.

    These jobs fan a burst of sequential CAPTCHA-gated requests out at the
    eCourts portal; running two at once caused a production outage, so only
    one of each may be in flight across the WHOLE system at a time. The
    caller should surface a "try again shortly" message, not queue behind
    the running one.
    """


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
        ("cancelled", "Cancelled"),
    ]

    JOB_TYPE_CHOICES = [
        ("document", "Document Processing"),
        ("order_sync", "Court Order Sync"),
        ("advocate_import", "Advocate Case Import"),
        ("advocate_search", "Advocate Search (state-wide fan-out)"),
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
    # "advocate_import" jobs carry their input (selected search results to
    # fetch) here and overwrite it with the outcome
    # ({"created": [...], "skipped_duplicate": [...], "skipped_conflict":
    # [...], "failed": [...]}) on completion -- case is left null since one
    # job creates many Case rows, not one. Unused by "document"/"order_sync".
    payload = models.JSONField(blank=True, null=True)
    # How many times this job has been claimed. Guards against a crash
    # loop: a job that keeps killing the worker is failed permanently
    # after MAX_ATTEMPTS (see process_jobs) instead of requeueing forever.
    attempts = models.IntegerField(default=0)
    # Cooperative cancellation flag for the advocate_search fan-out (see
    # request_cancel() below). The worker holds the row while "running",
    # so cancelling a running job can only raise this flag -- the fan-out
    # itself polls it at its per-district checkpoint (the same one used
    # for incremental payload persistence) and finishes the job as
    # "cancelled" from inside run_advocate_search. Unused by other job
    # types for now.
    cancel_requested = models.BooleanField(default=False)

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

    @classmethod
    def active_of_type_exists(cls, job_type: str) -> bool:
        """True if any queued/running job of this type exists, SYSTEM-WIDE
        (not scoped to an owner). Used to enforce the single-in-flight cap
        on the advocate_* portal jobs."""
        return cls.objects.filter(job_type=job_type, status__in=["queued", "running"]).exists()

    @classmethod
    def active_of_type_for_owner(cls, job_type: str, owner):
        """Queued/running jobs of this type belonging to `owner`, newest
        first. Owner-scoped (not system-wide like active_of_type_exists)
        because this backs a caller-facing "your in-progress searches"
        list -- another owner's job payload (search terms, partial
        results) must never be visible here, same posture as every other
        view in this module."""
        return cls.objects.filter(
            job_type=job_type, owner=owner, status__in=["queued", "running"]
        ).order_by("-created_at")

    def request_cancel(self) -> "ProcessingJob":
        """Cancel this job if it's queued or running; no-op (job returned
        unchanged) if it has already reached a terminal state.

        A queued job (the worker hasn't claimed it yet) is finished
        directly here via a conditional update, same tiny-race tolerance
        as enqueue_advocate_import's note above -- worst case the worker
        claims it in the same instant and the update below matches zero
        rows, which just falls through to the running-job branch.

        A running job can't be finished from here -- the worker owns the
        row while it's mid-fan-out -- so this only raises
        cancel_requested; run_advocate_search polls it at its
        per-district checkpoint and finishes the job as "cancelled" from
        inside the worker itself (see AdvocateSearchCancelled in
        core/services/advocate_search.py).
        """
        updated = ProcessingJob.objects.filter(pk=self.pk, status="queued").update(
            status="cancelled", cancel_requested=True, finished_at=timezone.now()
        )
        if updated:
            self.status = "cancelled"
            self.cancel_requested = True
            self.finished_at = timezone.now()
            return self

        updated = ProcessingJob.objects.filter(pk=self.pk, status="running").update(
            cancel_requested=True
        )
        if updated:
            self.cancel_requested = True
        else:
            self.refresh_from_db()
        return self

    @classmethod
    def enqueue_advocate_import(
        cls, owner, selected: list[dict], *, advocate_name: str = "", bar_code: str = ""
    ) -> "ProcessingJob":
        """Enqueue a bulk import of eCourts search results into new Cases.

        advocate_name/bar_code are the identity originally searched with
        (see core/views/advocate_search.py's AdvocateSearchImportView,
        which pulls these off the originating advocate_search job) --
        carried through so run_advocate_import can auto-detect each new
        Case's user_party_role against its freshly-fetched
        party_advocate_data. Both default to "" (no detection attempted)
        for callers that don't have/need it.

        No dedup against an existing job for the SAME batch -- each
        submission is distinct -- but only one advocate_import may run
        system-wide at a time (see JobAlreadyRunningError). The check and
        the create aren't in one lock, so a truly simultaneous double-submit
        could still slip a second job through; that's an acceptable, tiny
        race for a manually-triggered heavy job (same tolerance the preview
        throttle / refetch-interval checks already take), and the point is
        to stop the portal from being hit by two fan-outs at once."""
        if cls.active_of_type_exists("advocate_import"):
            raise JobAlreadyRunningError(
                "A case import is already running. Please wait for it to finish before adding more."
            )
        return cls.objects.create(
            owner=owner,
            job_type="advocate_import",
            payload={"selected": selected, "advocate_name": advocate_name, "bar_code": bar_code},
            progress_total=len(selected),
        )

    @classmethod
    def enqueue_advocate_search(cls, owner, params: dict) -> "ProcessingJob":
        """Enqueue a state-wide advocate search (fan-out across every
        district and court complex in a state -- see
        core/services/advocate_search.py). `params` carries the search
        inputs ({state_code, court_type, advocate_name, bar_code,
        status_filter}); the outcome ({results, failures, ...}) is written
        back into the same payload on completion.

        Only one advocate_search may run system-wide at a time (see
        JobAlreadyRunningError and enqueue_advocate_import's note on the
        check/create race)."""
        if cls.active_of_type_exists("advocate_search"):
            raise JobAlreadyRunningError(
                "A case search is already running. Please wait for it to finish before starting another."
            )
        return cls.objects.create(
            owner=owner,
            job_type="advocate_search",
            payload=dict(params),
        )
