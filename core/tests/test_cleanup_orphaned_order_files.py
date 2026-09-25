"""manage.py cleanup_orphaned_order_files: the PDFs 0037's row clean-up
left in storage. Dry run by default; never touches a referenced file, a
file outside the orders folder, or one written moments ago."""

import os
import time
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command

from core.models import Case, Document

PDF = b"%PDF-1.4\n%%EOF\n"


@pytest.fixture
def storage(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return tmp_path


def _age(path_on_disk, hours):
    past = time.time() - hours * 3600
    os.utime(path_on_disk, (past, past))


@pytest.fixture
def files(db, storage):
    owner = User.objects.create_user(username="orphan-owner", password="pw-12345")
    case = Case.objects.create(owner=owner, case_number="WP/1/2026", title="t", client_name="")
    kept = default_storage.save("documents/court_orders/HB_order_3_2026-08-14.pdf", ContentFile(PDF))
    orphan = default_storage.save("documents/court_orders/HB_order_2_2026-08-14.pdf", ContentFile(PDF))
    fresh = default_storage.save("documents/court_orders/HB_order_5_2026-09-20.pdf", ContentFile(PDF))
    elsewhere = default_storage.save("documents/unrelated.pdf", ContentFile(PDF))
    Document.objects.create(owner=owner, case=case, filename="o3.pdf", file_path=kept, file_type="pdf")
    for name in (kept, orphan, elsewhere):
        _age(default_storage.path(name), 48)
    return {"kept": kept, "orphan": orphan, "fresh": fresh, "elsewhere": elsewhere}


@pytest.mark.django_db
class TestCleanupOrphanedOrderFiles:
    def test_dry_run_lists_the_orphan_and_deletes_nothing(self, files):
        out = StringIO()
        call_command("cleanup_orphaned_order_files", stdout=out)

        text = out.getvalue()
        assert f"would delete: {files['orphan']}" in text
        assert files["kept"] not in text
        assert "[dry run] 1 orphaned file(s)" in text
        assert all(default_storage.exists(p) for p in files.values())

    def test_delete_removes_only_the_orphan(self, files):
        call_command("cleanup_orphaned_order_files", "--delete", stdout=StringIO())

        assert not default_storage.exists(files["orphan"])
        assert default_storage.exists(files["kept"])  # referenced by a Document
        assert default_storage.exists(files["fresh"])  # too new: maybe mid-sync
        assert default_storage.exists(files["elsewhere"])  # not in the orders folder

    def test_the_age_guard_is_adjustable(self, files):
        call_command("cleanup_orphaned_order_files", "--delete", "--min-age-hours", "0", stdout=StringIO())
        assert not default_storage.exists(files["fresh"])
        assert default_storage.exists(files["kept"])

    def test_no_orders_folder_is_fine(self, db, storage):
        out = StringIO()
        call_command("cleanup_orphaned_order_files", stdout=out)
        assert "nothing to do" in out.getvalue()
