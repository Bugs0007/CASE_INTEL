"""
Upload existing local media/ files to S3 and repoint Document.file_path at
the resulting keys.

Report-only by default -- prints what would be uploaded without touching S3
or the database. Pass --execute to actually upload and update rows. Reads
AWS credentials directly from the environment (independent of the USE_S3
toggle in settings.py), since this command is meant to be run to prepare S3
*before* flipping USE_S3=true.

Usage:
    python manage.py migrate_media_to_s3             # dry run (report only)
    python manage.py migrate_media_to_s3 --execute    # actually upload + update DB
"""

import os

import boto3
from botocore.exceptions import ClientError
from decouple import config
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Document


class Command(BaseCommand):
    help = (
        "Upload existing local media/ files to S3 and repoint Document.file_path "
        "at the new storage keys, verifying each upload by size. Report-only by "
        "default; pass --execute to actually upload and update the database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            default=False,
            help="Actually upload to S3 and update file_path (default: dry run / report only).",
        )

    def handle(self, *args, **options):
        execute = options["execute"]

        bucket_name = config("AWS_STORAGE_BUCKET_NAME", default="")
        region_name = config("AWS_S3_REGION_NAME", default="ap-south-1")
        access_key = config("AWS_ACCESS_KEY_ID", default="")
        secret_key = config("AWS_SECRET_ACCESS_KEY", default="")

        if not bucket_name or not access_key or not secret_key:
            raise CommandError(
                "AWS_STORAGE_BUCKET_NAME, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY "
                "must be set (in .env) to run this command, regardless of USE_S3."
            )

        s3 = boto3.client(
            "s3",
            region_name=region_name,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        mode = "EXECUTE" if execute else "DRY RUN (report only, nothing will be uploaded)"
        self.stdout.write(self.style.WARNING(f"Mode: {mode}"))
        self.stdout.write(f"Target bucket: {bucket_name} ({region_name})\n")

        documents = Document.objects.all().order_by("id")
        total = documents.count()
        uploaded = 0
        mismatched = 0
        missing = 0
        failed = 0

        for document in documents:
            local_path = self._resolve_local_path(document.file_path)

            if not local_path or not os.path.isfile(local_path):
                self.stdout.write(
                    self.style.ERROR(
                        f"[{document.id}] MISSING local file for file_path={document.file_path!r}"
                    )
                )
                missing += 1
                continue

            local_size = os.path.getsize(local_path)
            key = self._resolve_key(document.file_path, local_path)

            if not execute:
                self.stdout.write(
                    f"[{document.id}] would upload {local_path} "
                    f"({local_size} bytes) -> s3://{bucket_name}/{key}"
                )
                continue

            try:
                s3.upload_file(local_path, bucket_name, key)
                head = s3.head_object(Bucket=bucket_name, Key=key)
                remote_size = head["ContentLength"]
            except ClientError as exc:
                self.stdout.write(self.style.ERROR(f"[{document.id}] UPLOAD FAILED: {exc}"))
                failed += 1
                continue

            if remote_size != local_size:
                self.stdout.write(
                    self.style.ERROR(
                        f"[{document.id}] SIZE MISMATCH: local={local_size} "
                        f"remote={remote_size} (key={key}) -- file_path NOT updated"
                    )
                )
                mismatched += 1
                continue

            document.file_path = key
            document.save(update_fields=["file_path"])
            uploaded += 1
            self.stdout.write(self.style.SUCCESS(f"[{document.id}] uploaded + verified -> {key}"))

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. total={total} uploaded={uploaded} mismatched={mismatched} "
                f"missing={missing} failed={failed}"
            )
        )
        if not execute:
            self.stdout.write(
                "This was a dry run -- nothing was uploaded or changed in the database. "
                "Re-run with --execute to actually migrate."
            )

    @staticmethod
    def _resolve_local_path(file_path: str) -> str | None:
        """Resolve a Document.file_path value to an absolute local path.

        Handles both old rows (absolute filesystem paths, written before
        this migration) and new rows (storage-relative keys under
        MEDIA_ROOT, e.g. "documents/foo.pdf").
        """
        if not file_path:
            return None
        if os.path.isabs(file_path):
            return file_path
        return str(settings.MEDIA_ROOT / file_path)

    @staticmethod
    def _resolve_key(file_path: str, local_path: str) -> str:
        """Compute the S3 key to upload to.

        Relative file_path values are already the key. Old absolute paths
        are rebased onto MEDIA_ROOT when possible, falling back to
        documents/<basename> otherwise.
        """
        if not os.path.isabs(file_path):
            return file_path.replace(os.sep, "/")
        try:
            rel = os.path.relpath(local_path, settings.MEDIA_ROOT)
            if not rel.startswith(".."):
                return rel.replace(os.sep, "/")
        except ValueError:
            pass
        return f"documents/{os.path.basename(local_path)}"
