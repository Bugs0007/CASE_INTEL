"""
Create CourtOrder rows for order PDFs already sitting in storage.

Order sync (core/services/court_order_sync.py) writes the Document AND the
CourtOrder row together for every new download, so going forward nothing
needs backfilling. This command exists for files that landed before that
row existed, or whose CourtOrder write didn't happen -- it rebuilds the
metadata from the filename convention _order_filename() writes:

    documents/court_orders/<CNR>_order_<seq>_<YYYY-MM-DD>.pdf

Idempotent: Documents are matched on file_path and CourtOrders on
(case, dedup_key) -- the same unique constraint the sync path relies on --
so re-running imports nothing new. One unparseable/unresolvable file is
skipped and logged; it never aborts the scan.

Usage:
    python manage.py backfill_court_orders --dry-run   # report only
    python manage.py backfill_court_orders             # actually create rows
"""

import hashlib

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Case, CourtOrder, Document
from core.services.court_order_sync import ORDER_STORAGE_DIR, parse_order_filename


class Command(BaseCommand):
    help = (
        "Scan stored court-order PDFs and create any missing CourtOrder rows, "
        "parsing case/date/sequence out of the filename convention. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Report what would be imported without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN -- nothing will be written to the database.")
            )

        try:
            _dirs, filenames = default_storage.listdir(ORDER_STORAGE_DIR)
        except (FileNotFoundError, OSError):
            # Nothing has ever been downloaded on this deployment.
            self.stdout.write(f"No order storage directory at {ORDER_STORAGE_DIR!r} -- nothing to do.")
            return

        imported = 0
        existing = 0
        skipped = 0

        for filename in sorted(filenames):
            storage_key = f"{ORDER_STORAGE_DIR}/{filename}"

            record = parse_order_filename(filename)
            if record is None:
                # parse_order_filename already logged the specific reason.
                self.stdout.write(self.style.WARNING(f"SKIP {filename}: unparseable filename."))
                skipped += 1
                continue

            document = (
                Document.objects.select_related("case")
                .filter(file_path=storage_key)
                .first()
            )
            case = self._resolve_case(record.cnr, document)
            if case is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"SKIP {filename}: no unambiguous case for CNR {record.cnr!r}."
                    )
                )
                skipped += 1
                continue

            if CourtOrder.objects.filter(case=case, dedup_key=record.dedup_key).exists():
                existing += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"would import {filename} -> case {case.id} "
                    f"(order {record.order_number}, date {record.order_date})"
                )
                imported += 1
                continue

            with transaction.atomic():
                if document is None:
                    document = self._create_document(case, storage_key, filename, record)
                CourtOrder.objects.create(
                    owner=case.owner,
                    case=case,
                    order_number=record.order_number,
                    order_date=record.order_date,
                    description=record.description,
                    judge=record.judge,
                    source="ecourts",
                    dedup_key=record.dedup_key,
                    document=document,
                )
            imported += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"imported {filename} -> case {case.id} (order {record.order_number})"
                )
            )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. imported={imported} already-present={existing} skipped={skipped}"
            )
        )
        if dry_run:
            self.stdout.write("This was a dry run -- re-run without --dry-run to write rows.")

    @staticmethod
    def _resolve_case(cnr: str, document: Document | None) -> Case | None:
        """Find the Case an order file belongs to.

        Case.cnr_number is indexed but NOT unique -- two advocates can each
        track the same CNR -- so an existing Document for this exact
        storage key wins, since it already carries the right owner/case. A
        CNR matching several cases is ambiguous and gets skipped rather
        than guessed at: attaching an order to the wrong advocate's case
        would leak it across tenants.
        """
        if document is not None and document.case_id is not None:
            return document.case

        matches = list(Case.objects.filter(cnr_number=cnr)[:2])
        if len(matches) == 1:
            return matches[0]
        return None

    @staticmethod
    def _create_document(case: Case, storage_key: str, filename: str, record) -> Document:
        """Recreate the Document row for an orphaned order PDF.

        processing_status stays "pending" and no ProcessingJob is enqueued
        -- backfill is metadata repair, and kicking off OCR/embedding for
        every historical order at once would swamp the worker. Run
        POST /api/documents/<id>/process/ (or the admin) for any that
        genuinely need indexing.
        """
        content_hash = None
        file_size = None
        try:
            with default_storage.open(storage_key, "rb") as fh:
                raw = fh.read()
            content_hash = hashlib.sha256(raw).hexdigest()
            file_size = len(raw)
        except Exception:  # noqa: BLE001 -- unreadable file still gets its row
            pass

        return Document.objects.create(
            owner=case.owner,
            case=case,
            filename=filename,
            file_path=storage_key,
            file_type="pdf",
            file_size=file_size,
            document_type="court_order",
            document_date=record.order_date,
            processing_status="pending",
            content_hash=content_hash,
        )
