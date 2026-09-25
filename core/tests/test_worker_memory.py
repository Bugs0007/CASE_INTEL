"""The process_jobs worker's memory: recycling between jobs, streamed PDF
extraction, and spaCy imported without torch.

Measured on the Refresh-all run that prompted this: the worker sat at
~175MB, then jumped to ~400MB resident on the first document job and never
came back down. Most of that jump was torch, imported by spaCy's ML layer
for a sentence splitter that never uses it.
"""

import os
import subprocess
import sys
import textwrap
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from core.management.commands.process_jobs import RECYCLE_EXIT_CODE, Command
from core.models import Case, ProcessingJob
from core.services import document_processor as dp
from core.services.process_memory import current_rss_mb

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRss:
    def test_reads_this_processes_memory(self):
        rss = current_rss_mb()
        assert rss is not None and 10 < rss < 4000


class TestRecycleReason:
    def test_job_limit(self):
        assert Command._recycle_reason(200, 200, 0) == "200 jobs run (limit 200)"
        assert Command._recycle_reason(199, 200, 0) == ""

    def test_memory_limit(self):
        with patch("core.management.commands.process_jobs.current_rss_mb", return_value=412.0):
            assert Command._recycle_reason(1, 0, 300) == "resident memory 412 MB is over 300 MB"
        with patch("core.management.commands.process_jobs.current_rss_mb", return_value=250.0):
            assert Command._recycle_reason(1, 0, 300) == ""

    def test_zero_turns_both_limits_off(self):
        with patch("core.management.commands.process_jobs.current_rss_mb", return_value=9999.0):
            assert Command._recycle_reason(10_000, 0, 0) == ""

    def test_unknown_memory_never_recycles(self):
        with patch("core.management.commands.process_jobs.current_rss_mb", return_value=None):
            assert Command._recycle_reason(1, 0, 300) == ""


@pytest.fixture(autouse=False)
def keep_test_connection():
    # The loop's close_old_connections() would close the test transaction's
    # connection (autocommit differs inside it); the worker never runs
    # inside one for real.
    with patch("core.management.commands.process_jobs.close_old_connections"):
        yield


@pytest.mark.django_db
@pytest.mark.usefixtures("keep_test_connection")
class TestWorkerRecycles:
    def _queue(self, n):
        owner = User.objects.create_user(username="recycle-owner", password="pw-12345")
        case = Case.objects.create(owner=owner, case_number="OS/1/2026", title="t", client_name="")
        return [
            ProcessingJob.objects.create(owner=owner, case=case, job_type="case_briefing", status="queued")
            for _ in range(n)
        ]

    def test_exits_for_systemd_between_jobs_after_the_job_limit(self):
        jobs = self._queue(3)
        with patch.object(Command, "_process_job") as run, pytest.raises(SystemExit) as exit_info:
            call_command("process_jobs", "--once", "--max-jobs", "2", "--max-rss-mb", "0", stdout=StringIO())

        assert exit_info.value.code == RECYCLE_EXIT_CODE
        assert run.call_count == 2  # the third job waits for the fresh process
        assert ProcessingJob.objects.get(id=jobs[2].id).status == "queued"

    def test_exits_when_memory_is_over_the_limit(self):
        self._queue(2)
        with patch.object(Command, "_process_job") as run, \
                patch("core.management.commands.process_jobs.current_rss_mb", return_value=512.0), \
                pytest.raises(SystemExit) as exit_info:
            call_command("process_jobs", "--once", "--max-jobs", "0", "--max-rss-mb", "300", stdout=StringIO())

        assert exit_info.value.code == RECYCLE_EXIT_CODE
        assert run.call_count == 1

    def test_drains_normally_under_the_limits(self):
        self._queue(2)
        with patch.object(Command, "_process_job") as run:
            call_command("process_jobs", "--once", "--max-jobs", "0", "--max-rss-mb", "0", stdout=StringIO())
        assert run.call_count == 2  # returned normally: exit code 0, no restart needed


def _pdf(pages: int) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    for n in range(1, pages + 1):
        pdf.add_page()
        pdf.set_font("Helvetica", size=12)
        pdf.cell(0, 10, f"This is page {n} of the order.")
    return bytes(pdf.output())


@pytest.mark.django_db
class TestStreamedPdfExtraction:
    def test_every_page_in_order_across_reader_batches(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        name = default_storage.save("documents/long.pdf", ContentFile(_pdf(45)))

        text, pages = dp.DocumentProcessor._extract_pdf_with_page_count(name)

        assert pages == 45 > dp.PDF_PAGE_BATCH * 2
        positions = [text.index(f"This is page {n} of the order.") for n in range(1, 46)]
        assert positions == sorted(positions)

    def test_remote_storage_is_spooled_to_disk_and_cleaned_up(self, settings, tmp_path):
        settings.MEDIA_ROOT = str(tmp_path)
        name = default_storage.save("documents/remote.pdf", ContentFile(_pdf(3)))
        seen = []
        real_unlink = os.unlink

        def unlink(path):
            seen.append(path)
            real_unlink(path)

        class RemoteStorage:
            """Like S3Storage: open() works, there is no local path()."""

            def open(self, name, mode="rb"):
                return default_storage.open(name, mode)

            def path(self, name):
                raise NotImplementedError

        with patch("core.services.document_processor.default_storage", RemoteStorage()), \
                patch("core.services.document_processor.os.unlink", side_effect=unlink):
            text, pages = dp.DocumentProcessor._extract_pdf_with_page_count(name)

        assert pages == 3 and "This is page 3" in text
        assert seen and not os.path.exists(seen[0])


def test_spacy_is_imported_without_torch():
    """In a fresh interpreter, as in the worker: the sentence splitter
    works, torch was never imported, and torch is still importable after."""
    script = textwrap.dedent(
        """
        import os, sys
        sys.path.insert(0, r"%s")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "case_intel_project.settings")
        import django
        django.setup()
        from core.services.document_processor import DocumentProcessor
        nlp = DocumentProcessor()._get_nlp()
        sentences = [s.text for s in nlp("The petition is disposed of. No costs.").sents]
        print("sentences", sentences)
        print("torch_loaded", "torch" in sys.modules)
        try:
            import torch  # noqa: F401
            print("torch_importable_after", True)
        except ImportError:
            print("torch_importable_after", "not installed")
        """
        % REPO
    )
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=180).stdout
    assert "sentences ['The petition is disposed of.', 'No costs.']" in out
    assert "torch_loaded False" in out
    assert "torch_importable_after True" in out or "torch_importable_after not installed" in out
