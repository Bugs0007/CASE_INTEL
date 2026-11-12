"""Render an approved draft revision as a DOCX file (python-docx).

The same revision always gives the same bytes: the document's core
properties and the zip entry timestamps are pinned to the approval time.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import timezone as dt_timezone

from docx import Document

from core.services.india_time import india_fmt
from core.services.parties import case_court_name

# XML 1.0 cannot carry these; python-docx raises on them.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _clean(value) -> str:
    return _CONTROL_CHARS.sub("", str(value or ""))


def _block_text(block: dict, text: str) -> str:
    return f"Suggestion: {text}" if block.get("is_suggestion") else text


def _add_block(doc, block: dict) -> None:
    kind = block.get("type")
    if kind == "paragraph":
        doc.add_paragraph(_block_text(block, _clean(block.get("text"))))
    elif kind == "bullets":
        if block.get("is_suggestion"):
            doc.add_paragraph("Suggestion:")
        for item in block.get("items") or []:
            doc.add_paragraph(_clean(item), style="List Bullet")
    elif kind == "table":
        if block.get("is_suggestion"):
            doc.add_paragraph("Suggestion:")
        columns = block.get("columns") or []
        rows = block.get("rows") or []
        table = doc.add_table(rows=1, cols=len(columns))
        table.style = "Table Grid"
        for cell, column in zip(table.rows[0].cells, columns):
            cell.text = ""
            cell.paragraphs[0].add_run(_clean(column)).bold = True
        for row in rows:
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = _clean(value)
        doc.add_paragraph("")


def _pin_zip_times(data: bytes, stamp) -> bytes:
    """Rewrite the package with fixed entry timestamps (python-docx stamps
    each entry with the current time)."""
    date_time = (max(stamp.year, 1980), stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(
        out, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for name in source.namelist():
            info = zipfile.ZipInfo(name, date_time=date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(info, source.read(name))
    return out.getvalue()


def render_docx(revision) -> bytes:
    """The DOCX bytes for an approved revision."""
    body = revision.body
    case = revision.draft.case
    approved_utc = revision.approved_at.astimezone(dt_timezone.utc).replace(tzinfo=None, microsecond=0)

    doc = Document()
    title = _clean(body.get("title"))
    doc.add_heading(title, level=0)

    case_line = [_clean(case.title), _clean(case.case_number)]
    court = _clean(case_court_name(case))
    if court:
        case_line.append(court)
    doc.add_paragraph(", ".join(part for part in case_line if part))
    doc.add_paragraph(
        "Prepared with Case Intel from the approved draft, "
        f"version {revision.version}, {india_fmt(revision.approved_at)}."
    )

    for section in body.get("sections") or []:
        doc.add_heading(_clean(section.get("heading")), level=1)
        for block in section.get("blocks") or []:
            _add_block(doc, block)

    items = body.get("verification_items") or []
    if items:
        doc.add_heading("Items to verify", level=1)
        for item in items:
            doc.add_paragraph(_clean(item), style="List Bullet")

    props = doc.core_properties
    props.title = title
    props.author = "Case Intel"
    props.last_modified_by = "Case Intel"
    props.created = approved_utc
    props.modified = approved_utc
    props.revision = 1

    buffer = io.BytesIO()
    doc.save(buffer)
    return _pin_zip_times(buffer.getvalue(), approved_utc)
