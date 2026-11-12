"""Render a practice report (reports.build_report) as a PDF or a DOCX.

Pure functions of the report dict: no database, no model, nothing written to
disk. PDF uses fpdf2 (core fonts, so text goes through pdf_safe); DOCX uses
python-docx.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone as dt_timezone

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Mm

from core.services.pdf_utils import pdf_safe

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def filename(report: dict, fmt: str) -> str:
    start, end = report.get("date_from"), report.get("date_to")
    span = f"-{start}-to-{end}" if start and end else ""
    return f"{report['kind']}-report{span}.{fmt}"


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def render_pdf(report: dict) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(12, 12, 12)
    pdf.add_page()
    usable = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, pdf_safe(report["title"]), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, pdf_safe(f"Period: {report['period_text']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, pdf_safe(f"Generated on {report['generated_on']} (India time)"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for block in report["blocks"]:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, pdf_safe(block["heading"]), new_x="LMARGIN", new_y="NEXT")
        if block["type"] == "summary":
            pdf.set_font("Helvetica", "", 10)
            for label, value in block["items"]:
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(80, 6, pdf_safe(label))
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, pdf_safe(value), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            continue
        if not block["rows"]:
            pdf.set_font("Helvetica", "I", 10)
            pdf.cell(0, 6, pdf_safe(block.get("empty") or "Nothing to show."), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            continue
        weights = block.get("weights") or [1] * len(block["columns"])
        scale = usable / sum(weights)
        widths = tuple(w * scale for w in weights)
        pdf.set_font("Helvetica", "", 8)
        with pdf.table(col_widths=widths, line_height=4.5, text_align="LEFT", repeat_headings=1) as table:
            header = table.row()
            for column in block["columns"]:
                header.cell(pdf_safe(column), style=_bold())
            for row in block["rows"]:
                line = table.row()
                for cell in row:
                    line.cell(pdf_safe(cell))
        if block.get("note"):
            pdf.set_font("Helvetica", "I", 8)
            pdf.cell(0, 5, pdf_safe(block["note"]), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    return bytes(pdf.output())


def _bold():
    from fpdf.fonts import FontFace

    return FontFace(emphasis="BOLD")


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def _clean(value) -> str:
    return _CONTROL_CHARS.sub("", str(value or ""))


def render_docx(report: dict) -> bytes:
    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Mm(297), Mm(210)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, side, Mm(15))

    doc.add_heading(_clean(report["title"]), level=1)
    doc.add_paragraph(_clean(f"Period: {report['period_text']}"))
    doc.add_paragraph(_clean(f"Generated on {report['generated_on']} (India time)"))

    for block in report["blocks"]:
        doc.add_heading(_clean(block["heading"]), level=2)
        if block["type"] == "summary":
            table = doc.add_table(rows=0, cols=2)
            table.style = "Table Grid"
            for label, value in block["items"]:
                cells = table.add_row().cells
                cells[0].text = _clean(label)
                cells[1].text = ""
                cells[1].paragraphs[0].add_run(_clean(value)).bold = True
            continue
        if not block["rows"]:
            doc.add_paragraph(_clean(block.get("empty") or "Nothing to show."))
            continue
        columns = block["columns"]
        table = doc.add_table(rows=1, cols=len(columns))
        table.style = "Table Grid"
        for cell, column in zip(table.rows[0].cells, columns):
            cell.text = ""
            cell.paragraphs[0].add_run(_clean(column)).bold = True
        for row in block["rows"]:
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = _clean(value)
        if block.get("note"):
            doc.add_paragraph(_clean(block["note"]))

    stamp = datetime.now(dt_timezone.utc)
    props = doc.core_properties
    props.title = _clean(report["title"])
    props.author = "Case Intel"
    props.last_modified_by = "Case Intel"
    props.created = stamp
    props.modified = stamp
    props.revision = 1

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def render(report: dict, fmt: str) -> bytes:
    if fmt == "pdf":
        return render_pdf(report)
    if fmt == "docx":
        return render_docx(report)
    raise ValueError(f"Unknown format {fmt!r}.")
