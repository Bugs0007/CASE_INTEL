from django.db import models
from django.utils import timezone

from .mixins import OwnedModel
from .processing_job import ProcessingJob


class InvalidComplexRunTransition(ValueError):
    """A court-complex run was moved to a status it cannot go to from where it is."""


class AdvocateSearchComplexRun(OwnedModel):
    """One court complex's part of one advocate search: what the status screen
    lists, line by line, while the search runs ("Adilabad Court Complex, 6
    matched, 38 s"; "Bhainsa Court Complex, portal disconnected, 3 attempts").

    A row is created `pending` when the court's district has been listed, goes
    `running` while the worker is on it and ends `done` or `failed`. It is
    written as soon as the complex finishes, so "Found so far" and the court list
    fill in live. A failed row is not retried again by itself: after the
    provider's own bounded attempts it stays `failed` until the advocate asks
    for a retry, which creates a child job for just those rows (see
    core/services/advocate_search_v2.py) and sends the row back to `pending`.

    status transitions (enforced here, nowhere else assigns `status`):
        pending -> running -> done | failed
        failed  -> pending            (the advocate asked to search it again)
        done    -> pending            (same, for a court that found nothing and should be re-read)
    """

    PENDING, RUNNING, DONE, FAILED = "pending", "running", "done", "failed"
    STATUS_CHOICES = [(PENDING, "Waiting"), (RUNNING, "Searching"), (DONE, "Done"), (FAILED, "Failed")]
    TRANSITIONS = {
        PENDING: {RUNNING},
        RUNNING: {DONE, FAILED},
        FAILED: {PENDING},
        DONE: {PENDING},
    }

    # last_error_code: what went wrong, in the few kinds the screen can explain.
    PORTAL_DISCONNECT = "portal_disconnect"
    CAPTCHA_FAILED = "captcha_failed"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    PORTAL_ERROR = "portal_error"
    ERROR_CODE_CHOICES = [
        (PORTAL_DISCONNECT, "Portal disconnected"),
        (CAPTCHA_FAILED, "Captcha not solved"),
        (TIMEOUT, "Portal timed out"),
        (PARSE_ERROR, "Answer could not be read"),
        (PORTAL_ERROR, "Portal refused the request"),
    ]

    job = models.ForeignKey(ProcessingJob, on_delete=models.CASCADE, related_name="complex_runs")
    dist_code = models.CharField(max_length=20)
    dist_name = models.CharField(max_length=255, blank=True, default="")
    # Empty complex_code marks a district whose list of courts could not be read:
    # one failed row standing for "every court in this district".
    complex_code = models.CharField(max_length=40, blank=True, default="")
    est_code = models.CharField(max_length=40, blank=True, default="")
    complex_name = models.CharField(max_length=255, blank=True, default="")
    query = models.TextField(
        blank=True,
        default="",
        help_text="What was searched here: the name queries joined by ' | ', or the bar code.",
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    attempts = models.PositiveSmallIntegerField(
        default=0, help_text="Portal attempts spent on this court in its latest round (all queries together)."
    )
    last_error_code = models.CharField(max_length=20, blank=True, default="", choices=ERROR_CODE_CHOICES)
    last_error_message = models.CharField(max_length=255, blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    raw_count = models.PositiveIntegerField(default=0, help_text="Rows the court returned.")
    matched_count = models.PositiveIntegerField(
        default=0, help_text="Rows that were matched or worth checking against the profile when the court finished."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "advocate_search_complex_runs"
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "dist_code", "complex_code", "est_code"], name="one_run_per_court_complex_per_job"
            )
        ]
        indexes = [models.Index(fields=["job", "status"])]

    def __str__(self):
        return f"{self.complex_name or self.dist_name} [{self.status}]"

    # -- the state machine -------------------------------------------------

    def _move(self, new_status: str) -> None:
        if new_status not in self.TRANSITIONS.get(self.status, set()):
            raise InvalidComplexRunTransition(f"A court complex run cannot go from {self.status!r} to {new_status!r}.")
        self.status = new_status

    def mark_running(self) -> None:
        self._move(self.RUNNING)
        self.started_at = timezone.now()
        self.finished_at = None
        self.save(update_fields=["status", "started_at", "finished_at", "updated_at"])

    def mark_done(self, *, attempts: int, raw_count: int, matched_count: int) -> None:
        self._move(self.DONE)
        self.attempts = attempts
        self.raw_count = raw_count
        self.matched_count = matched_count
        self.last_error_code = ""
        self.last_error_message = ""
        self.finished_at = timezone.now()
        self.save(
            update_fields=[
                "status", "attempts", "raw_count", "matched_count", "last_error_code",
                "last_error_message", "finished_at", "updated_at",
            ]
        )

    def mark_failed(
        self, *, attempts: int, error_code: str, error_message: str, raw_count: int = 0, matched_count: int = 0
    ) -> None:
        """`raw_count`/`matched_count` carry what a court that failed part-way (one
        of two queries read) still returned."""
        self._move(self.FAILED)
        self.attempts = attempts
        self.last_error_code = error_code
        self.last_error_message = error_message[:255]
        self.raw_count = raw_count
        self.matched_count = matched_count
        self.finished_at = timezone.now()
        self.save(
            update_fields=[
                "status", "attempts", "last_error_code", "last_error_message", "raw_count",
                "matched_count", "finished_at", "updated_at",
            ]
        )

    def reset_for_retry(self) -> None:
        """The advocate asked for this court to be searched again."""
        self._move(self.PENDING)
        self.attempts = 0
        self.last_error_code = ""
        self.last_error_message = ""
        self.started_at = None
        self.finished_at = None
        self.save(
            update_fields=[
                "status", "attempts", "last_error_code", "last_error_message", "started_at",
                "finished_at", "updated_at",
            ]
        )
