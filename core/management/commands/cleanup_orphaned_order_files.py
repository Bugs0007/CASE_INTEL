"""Delete court-order PDFs in storage that no database row points at.

Migration 0037 removed the duplicate order rows (and their Document rows)
that the portal's renumbering had created, but deliberately left the PDF
files in storage -- a migration shouldn't delete files. This finds them:
every file under documents/court_orders/ that no Document, DocumentVersion,
EmailAttachment or TravelBooking references.

DRY RUN BY DEFAULT: it only prints what it would delete. Pass --delete to
delete. Files younger than --min-age-hours (default 1) are always skipped:
an order sync saves the PDF a moment before it creates the Document row,
and a file caught in that gap is not an orphan.

    python manage.py cleanup_orphaned_order_files
    python manage.py cleanup_orphaned_order_files --delete
"""

from datetime import timedelta

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Document, DocumentVersion, EmailAttachment, TravelBooking
from core.services.court_order_sync import ORDER_STORAGE_DIR


def referenced_paths() -> set[str]:
    paths: set[str] = set()
    for model in (Document, DocumentVersion, EmailAttachment, TravelBooking):
        paths.update(p for p in model.objects.exclude(file_path__isnull=True).values_list("file_path", flat=True) if p)
    return paths


class Command(BaseCommand):
    help = "List (or, with --delete, delete) court-order PDFs in storage that no row references."

    def add_arguments(self, parser):
        parser.add_argument("--delete", action="store_true", help="Delete the orphans (default: dry run).")
        parser.add_argument(
            "--min-age-hours",
            type=float,
            default=1.0,
            help="Skip files modified more recently than this (default 1).",
        )

    def handle(self, *args, **options):
        delete = options["delete"]
        cutoff = timezone.now() - timedelta(hours=options["min_age_hours"])
        try:
            _dirs, files = default_storage.listdir(ORDER_STORAGE_DIR)
        except FileNotFoundError:
            self.stdout.write(f"No {ORDER_STORAGE_DIR}/ in storage -- nothing to do.")
            return

        referenced = referenced_paths()
        orphans, too_new, total_bytes = [], 0, 0
        for name in sorted(files):
            path = f"{ORDER_STORAGE_DIR}/{name}"
            if path in referenced:
                continue
            try:
                modified = default_storage.get_modified_time(path)
            except (NotImplementedError, OSError):
                modified = None
            if modified is not None and modified > cutoff:
                too_new += 1
                continue
            try:
                size = default_storage.size(path)
            except (NotImplementedError, OSError):
                size = 0
            orphans.append((path, size, modified))
            total_bytes += size

        verb = "delete" if delete else "would delete"
        for path, size, modified in orphans:
            when = f", modified {modified:%Y-%m-%d %H:%M}" if modified else ""
            self.stdout.write(f"{verb}: {path} ({size / 1024:.0f} KB{when})")
            if delete:
                default_storage.delete(path)

        summary = (
            f"{len(orphans)} orphaned file(s), {total_bytes / (1024 * 1024):.1f} MB, "
            f"out of {len(files)} in {ORDER_STORAGE_DIR}/"
            + (f"; {too_new} newer than the age limit left alone" if too_new else "")
        )
        if delete:
            self.stdout.write(self.style.SUCCESS(f"Deleted {summary}."))
        else:
            self.stdout.write(self.style.WARNING(f"[dry run] {summary}. Nothing deleted -- pass --delete."))
