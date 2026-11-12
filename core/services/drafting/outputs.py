"""Release an approved draft revision as a DOCX file or a saved case note.

One DraftOutput row per (revision, destination): a repeated request returns
the same output and never writes a second file or a second note.
"""

from __future__ import annotations

import hashlib
import logging
import re
import unicodedata

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction

from core.models import AssistantDraft, AssistantDraftRevision, CaseNote, DraftOutput
from core.services.drafting.approval import DraftConflict, DraftNotFound, body_hash
from core.services.drafting.docx_render import render_docx

logger = logging.getLogger(__name__)

DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
STORAGE_ERROR = "The file could not be saved. Try again."


class OutputStorageError(Exception):
    """The DOCX could not be written to storage. The row is marked failed."""


def body_to_text(body: dict) -> str:
    """Plain text of a draft body: what a saved case note holds."""
    lines: list[str] = []
    for section in body.get("sections") or []:
        lines.append(str(section.get("heading") or ""))
        for block in section.get("blocks") or []:
            kind = block.get("type")
            suggestion = bool(block.get("is_suggestion"))
            if kind == "paragraph":
                text = str(block.get("text") or "")
                lines.append(f"Suggestion: {text}" if suggestion else text)
            elif kind == "bullets":
                if suggestion:
                    lines.append("Suggestion:")
                lines.extend(f"- {item}" for item in block.get("items") or [])
            elif kind == "table":
                if suggestion:
                    lines.append("Suggestion:")
                lines.append(" | ".join(block.get("columns") or []))
                lines.extend(" | ".join(row) for row in block.get("rows") or [])
        lines.append("")
    items = body.get("verification_items") or []
    if items:
        lines.append("Items to verify")
        lines.extend(f"- {item}" for item in items)
    return "\n".join(lines).strip()


def docx_filename(title: str) -> str:
    ascii_title = (
        unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    )
    stem = re.sub(r"[^A-Za-z0-9 _-]+", "", ascii_title)
    stem = re.sub(r"\s+", " ", stem).strip()[:80].strip()
    return f"{stem or 'draft'}.docx"


def storage_key(revision: AssistantDraftRevision) -> str:
    return f"draft_outputs/{revision.owner_id}/{revision.draft_id}/r{revision.version}.docx"


def _reserve(revision, destination, user) -> DraftOutput:
    """The locked (revision, destination) row, created if needed."""
    try:
        with transaction.atomic():
            DraftOutput.objects.get_or_create(
                revision=revision, destination=destination, defaults={"owner": user}
            )
    except IntegrityError:
        pass  # a concurrent request created it; the locked read below finds it
    return DraftOutput.objects.select_for_update().get(
        owner=user, revision=revision, destination=destination
    )


def _write_docx(output: DraftOutput, revision: AssistantDraftRevision) -> bool:
    data = render_docx(revision)
    key = storage_key(revision)
    try:
        if default_storage.exists(key):
            default_storage.delete(key)
        saved = default_storage.save(key, ContentFile(data))
    except Exception as exc:
        logger.error(
            "Draft output %s: storage write failed (%s)", output.id, type(exc).__name__
        )
        try:
            if default_storage.exists(key):
                default_storage.delete(key)
        except Exception:
            pass
        output.status = DraftOutput.STATUS_FAILED
        output.error = STORAGE_ERROR
        output.file_path = ""
        output.checksum = ""
        output.save()
        return False
    output.file_path = saved
    output.filename = docx_filename(revision.body.get("title", ""))
    output.checksum = hashlib.sha256(data).hexdigest()
    return True


def _save_note(output: DraftOutput, revision: AssistantDraftRevision, draft, user) -> None:
    note = CaseNote.objects.filter(owner=user, origin_revision=revision).first()
    if note is None:
        note = CaseNote.objects.create(
            owner=user,
            case=draft.case,
            title=revision.body.get("title", "")[:200],
            body=body_to_text(revision.body),
            origin_revision=revision,
        )
    output.case_note = note


def create_output(*, draft_id, revision_id, user, destination) -> tuple[DraftOutput, bool]:
    """(output, created_now). Raises DraftNotFound, DraftConflict
    (`not_approved`) or OutputStorageError."""
    with transaction.atomic():
        draft = (
            AssistantDraft.objects.select_related("case")
            .filter(owner=user, pk=draft_id)
            .first()
        )
        if draft is None:
            raise DraftNotFound()
        revision = (
            AssistantDraftRevision.objects.select_related("draft__case")
            .filter(owner=user, draft=draft, pk=revision_id)
            .first()
        )
        if revision is None:
            raise DraftNotFound()
        if revision.approved_at is None or body_hash(revision.body) != revision.approved_hash:
            raise DraftConflict(
                "not_approved", "Approve this version before exporting or saving it."
            )

        output = _reserve(revision, destination, user)
        done = output.status == DraftOutput.STATUS_READY and (
            destination == DraftOutput.DEST_DOCX or output.case_note_id is not None
        )
        if done:
            return output, False

        # New, failed, or a pending row whose request died: finish it in place.
        if destination == DraftOutput.DEST_DOCX:
            stored = _write_docx(output, revision)
        else:
            _save_note(output, revision, draft, user)
            stored = True
        if stored:
            output.status = DraftOutput.STATUS_READY
            output.error = ""
            output.save()

    # Raised after the transaction so the failed row is committed.
    if not stored:
        raise OutputStorageError(STORAGE_ERROR)
    return output, True


def read_docx(output: DraftOutput) -> bytes | None:
    """The stored file's bytes, or None when it is not there."""
    try:
        if not output.file_path or not default_storage.exists(output.file_path):
            return None
        with default_storage.open(output.file_path, "rb") as handle:
            return handle.read()
    except Exception as exc:
        logger.error("Draft output %s: storage read failed (%s)", output.id, type(exc).__name__)
        return None
