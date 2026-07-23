"""
DB-backed document-processing worker.

Claims the oldest queued ProcessingJob with select_for_update(skip_locked),
runs the existing DocumentProcessor pipeline on it (extract -> OCR if the
PDF is scanned -> chunk -> embed in batches -> save), and reports progress
on the job row after every chunk-batch.

This is the no-Redis replacement for a Celery worker (see the Celery
section in settings.py): Postgres row locking is the queue, and this
command runs as a long-lived loop under systemd
(deploy/case-intel-worker.service).

Crash safety: a heartbeat thread bumps the running job's updated_at every
HEARTBEAT_SECONDS. If the worker dies mid-job, the job is left "running"
with a heartbeat that stops advancing; the reclaim step at the top of the
loop requeues any running job whose heartbeat is older than
--stale-seconds (or fails it permanently after MAX_ATTEMPTS claims, so a
job that reliably kills the worker can't crash-loop forever).

Usage:
    python manage.py process_jobs                 # long-lived loop
    python manage.py process_jobs --once          # drain queue, then exit
"""

import logging
import threading
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections, connections, transaction
from django.utils import timezone

from core.models import Case, Document, ProcessingJob
from core.services.advocate_import import run_advocate_import
from core.services.court_order_sync import sync_case_orders
from core.services.document_processor import DocumentProcessor

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 3.0     # seconds between empty polls -- no busy loop
DEFAULT_STALE_SECONDS = 300     # running + no heartbeat for this long => reclaim
HEARTBEAT_SECONDS = 30
MAX_ATTEMPTS = 3


class Command(BaseCommand):
    help = "Run the background document-processing worker loop."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process jobs until the queue is empty, then exit "
                 "(instead of polling forever).",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=DEFAULT_POLL_INTERVAL,
            help=f"Seconds to sleep between empty polls (default {DEFAULT_POLL_INTERVAL}).",
        )
        parser.add_argument(
            "--stale-seconds",
            type=float,
            default=DEFAULT_STALE_SECONDS,
            help="Reclaim 'running' jobs whose heartbeat is older than this "
                 f"(default {DEFAULT_STALE_SECONDS}).",
        )

    def handle(self, *args, **options):
        once = options["once"]
        poll_interval = options["poll_interval"]
        stale_seconds = options["stale_seconds"]

        self.stdout.write("process_jobs worker started (poll=%ss, stale=%ss)"
                          % (poll_interval, stale_seconds))
        processor = DocumentProcessor()

        while True:
            close_old_connections()
            self._reclaim_stale_jobs(stale_seconds)

            job = self._claim_next_job()
            if job is None:
                if once:
                    self.stdout.write("Queue empty -- exiting (--once).")
                    return
                time.sleep(poll_interval)
                continue

            self._process_job(job, processor)

    # ------------------------------------------------------------------
    # Queue operations
    # ------------------------------------------------------------------

    def _claim_next_job(self):
        """Atomically claim the oldest queued job, or return None."""
        with transaction.atomic():
            job = (
                ProcessingJob.objects
                .select_for_update(skip_locked=True)
                .filter(status="queued")
                .order_by("created_at")
                .first()
            )
            if job is None:
                return None
            job.status = "running"
            job.attempts += 1
            job.started_at = timezone.now()
            job.progress_current = 0
            job.error = ""
            job.save(update_fields=[
                "status", "attempts", "started_at", "progress_current",
                "error", "updated_at",
            ])
        return job

    def _reclaim_stale_jobs(self, stale_seconds: float) -> None:
        """Requeue (or permanently fail) running jobs with a dead heartbeat."""
        cutoff = timezone.now() - timezone.timedelta(seconds=stale_seconds)
        stale = ProcessingJob.objects.filter(status="running", updated_at__lt=cutoff)
        for job in stale:
            if job.attempts >= MAX_ATTEMPTS:
                logger.error(
                    "Job %d (%s) crashed the worker %d times -- failing permanently.",
                    job.id, job, job.attempts,
                )
                job.status = "failed"
                job.error = (
                    f"Worker died mid-job {job.attempts} times "
                    f"(no heartbeat for {int(stale_seconds)}s); giving up."
                )
                job.finished_at = timezone.now()
                job.save(update_fields=["status", "error", "finished_at", "updated_at"])
                # No-op for order_sync jobs (document_id is None).
                Document.objects.filter(id=job.document_id).update(
                    processing_status="failed"
                )
            else:
                logger.warning(
                    "Job %d (%s) looks abandoned (heartbeat stale) -- requeueing "
                    "(attempt %d/%d).",
                    job.id, job, job.attempts, MAX_ATTEMPTS,
                )
                job.status = "queued"
                job.progress_current = 0
                job.save(update_fields=["status", "progress_current", "updated_at"])

    # ------------------------------------------------------------------
    # Job execution
    # ------------------------------------------------------------------

    def _process_job(self, job: ProcessingJob, processor: DocumentProcessor) -> None:
        self.stdout.write(f"Processing job {job.id} ({job}, attempt {job.attempts})")

        stop_heartbeat = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop, args=(job.id, stop_heartbeat), daemon=True
        )
        heartbeat.start()

        def report_progress(current: int, total: int) -> None:
            # .update() bypasses auto_now, so bump the heartbeat explicitly.
            ProcessingJob.objects.filter(id=job.id).update(
                progress_current=current,
                progress_total=total,
                updated_at=timezone.now(),
            )

        try:
            if job.job_type == "order_sync":
                self._run_order_sync(job, report_progress)
            elif job.job_type == "advocate_import":
                run_advocate_import(job, progress_callback=report_progress)
            else:
                processor.process_document(job.document_id, progress_callback=report_progress)
        except Document.DoesNotExist:
            self._finish(job, "failed", error=f"Document {job.document_id} no longer exists.")
        except Case.DoesNotExist:
            self._finish(job, "failed", error=f"Case {job.case_id} no longer exists.")
        except Exception as exc:
            # DocumentProcessor already marked the document itself failed.
            logger.exception("Job %d failed", job.id)
            self._finish(job, "failed", error=str(exc)[:2000])
        else:
            self._finish(job, "succeeded")
            self.stdout.write(self.style.SUCCESS(f"Job {job.id} succeeded."))
        finally:
            stop_heartbeat.set()
            heartbeat.join(timeout=5)

    def _run_order_sync(self, job: ProcessingJob, report_progress) -> None:
        """Fetch new court-order PDFs for the job's case. Each downloaded
        PDF gets its own document ProcessingJob, so this worker loop picks
        the files up for the normal extract/OCR/embed pipeline next."""
        case = Case.objects.get(id=job.case_id)
        result = sync_case_orders(case, progress_callback=report_progress)
        self.stdout.write(
            f"Order sync for case {case.id}: {result['listed']} listed, "
            f"{result['new']} new, {result['downloaded']} downloaded, "
            f"{result['failed']} failed."
        )

    @staticmethod
    def _finish(job: ProcessingJob, status: str, error: str = "") -> None:
        ProcessingJob.objects.filter(id=job.id).update(
            status=status,
            error=error,
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )

    @staticmethod
    def _heartbeat_loop(job_id: int, stop: threading.Event) -> None:
        """Bump updated_at while the job runs, even during long OCR phases
        that produce no chunk-batch progress callbacks."""
        try:
            while not stop.wait(HEARTBEAT_SECONDS):
                ProcessingJob.objects.filter(id=job_id, status="running").update(
                    updated_at=timezone.now()
                )
        finally:
            # This thread has its own DB connection -- close it explicitly.
            connections.close_all()
