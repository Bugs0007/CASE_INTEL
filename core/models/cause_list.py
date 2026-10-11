"""Cause-list bookkeeping (see core/services/causelists/).

Two tables, deliberately different in kind:

- `CauseListFetch` is an audit/idempotency ledger of what the system
  fetched from a court portal. It holds PUBLIC court metadata (a list's
  type, size and hash), never user data, so -- unlike every case-data model
  -- it is NOT an `OwnedModel`. It is written only by the fetch job and is
  not exposed through any API.
- `CauseListMatch` records where an advocate's own hearing sits in a
  published list. That is user data, so it carries `owner`. Only MATCHED
  entries are ever persisted; unmatched ones (other advocates' matters,
  ~99% of a list) are never stored.
"""

from django.db import models

from .mixins import OwnedModel


class CauseListFetch(models.Model):
    KIND_INDEX = "index"
    KIND_DOCUMENT = "document"
    KIND_CHOICES = [
        (KIND_INDEX, "Index (the portal's list of lists)"),
        (KIND_DOCUMENT, "Document (one list)"),
    ]

    # Index rows: ok / none_available / captcha_failed / fetch_error / skipped_locked.
    # Document rows: ok / empty_ok / not_uploaded / fetch_error / parse_failed.
    STATUS_OK = "ok"
    STATUS_EMPTY_OK = "empty_ok"
    STATUS_NONE_AVAILABLE = "none_available"
    STATUS_NOT_UPLOADED = "not_uploaded"
    STATUS_CAPTCHA_FAILED = "captcha_failed"
    STATUS_FETCH_ERROR = "fetch_error"
    STATUS_PARSE_FAILED = "parse_failed"
    STATUS_SKIPPED_LOCKED = "skipped_locked"
    STATUS_CHOICES = [
        (STATUS_OK, "OK"),
        (STATUS_EMPTY_OK, "Fetched; the list is genuinely empty"),
        (STATUS_NONE_AVAILABLE, "Court has no list for this date"),
        (STATUS_NOT_UPLOADED, "Listed by the court but not uploaded"),
        (STATUS_CAPTCHA_FAILED, "CAPTCHA budget exhausted"),
        (STATUS_FETCH_ERROR, "Fetch error"),
        (STATUS_PARSE_FAILED, "Fetched but could not be parsed"),
        (STATUS_SKIPPED_LOCKED, "Skipped: another portal job was active"),
    ]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    adapter = models.CharField(max_length=40)
    target_key = models.CharField(max_length=200)
    list_date = models.DateField()
    doc_key = models.CharField(max_length=200, blank=True, default="")
    list_type = models.CharField(max_length=200, blank=True, default="")
    bench_label = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    # Audit only for session-bound portals; a usable link only when
    # source_public is true.
    source_ref = models.CharField(max_length=600, blank=True, default="")
    source_public = models.BooleanField(default=False)
    sha256 = models.CharField(max_length=64, blank=True, default="")
    entry_count = models.IntegerField(default=0)
    doc_total = models.IntegerField(default=0)
    error = models.TextField(blank=True, default="")
    attempts = models.IntegerField(default=1)
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cause_list_fetches"
        constraints = [
            models.UniqueConstraint(
                fields=["adapter", "target_key", "list_date", "kind", "doc_key"],
                name="unique_cause_list_fetch",
            )
        ]
        indexes = [models.Index(fields=["list_date", "adapter"])]

    def __str__(self):
        return f"{self.adapter}:{self.target_key} {self.list_date} {self.kind} {self.status}"


class CauseListMatch(OwnedModel):
    """One place a hearing appears in a published list. A hearing can have
    several (a main list and a supplementary one, or several benches)."""

    MATCHED_BY_CNR = "cnr"
    MATCHED_BY_CASE_KEY = "case_key"

    hearing = models.ForeignKey(
        "core.Hearing", on_delete=models.CASCADE, related_name="cause_list_matches"
    )
    fetch = models.ForeignKey(
        CauseListFetch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="matches",
    )
    item_number = models.CharField(max_length=20, blank=True, default="")
    court_hall = models.CharField(max_length=20, blank=True, default="")
    court_name = models.CharField(max_length=300, blank=True, default="")
    bench = models.CharField(max_length=300, blank=True, default="")
    list_type = models.CharField(max_length=200, blank=True, default="")
    stage = models.CharField(max_length=200, blank=True, default="")
    connected = models.JSONField(blank=True, default=list)
    matched_by = models.CharField(max_length=10, default=MATCHED_BY_CASE_KEY)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cause_list_matches"
        ordering = ["hearing_id", "-is_primary", "id"]
        indexes = [models.Index(fields=["hearing", "is_primary"])]

    def __str__(self):
        return f"hearing {self.hearing_id}: item {self.item_number} ({self.list_type})"
