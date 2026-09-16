"""Render a hearing prep sheet as a one-to-two page PDF (fpdf2).

Renders the same dict the API returns (serialize_hearing_digest), so the
printed sheet and the screen always agree.
"""

from __future__ import annotations

from datetime import date, datetime

from django.utils import timezone

from core.services.pdf_utils import pdf_safe

_BRIEFING_PLACEHOLDER = {
    "missing": "Not generated yet -- open the prep sheet in Case Intel to generate it.",
    "generating": "Being generated -- download the sheet again in a minute.",
    "unavailable": "Nothing on record yet to summarise.",
}


def render_hearing_digest_pdf(data: dict) -> bytes:
    from fpdf import FPDF

    hearing = data["hearing"]
    case = data["case"]
    cause_list = hearing["cause_list"]

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    _line(pdf, "Hearing prep sheet", height=9)
    pdf.set_font("Helvetica", "", 11)
    _para(pdf, f"{case['case_number']} -- {case['title']}")
    pdf.ln(2)

    facts = [
        ("Hearing", _hearing_text(hearing)),
        ("For", "; ".join(data["purposes"])),
        ("Court", case["court_and_judge"] or hearing["location"]),
        ("Cause list", _cause_list_text(cause_list)),
        ("Case status", " / ".join(p for p in (case["case_status"], case["case_stage"]) if p)),
    ]
    for label, value in facts:
        if value:
            _fact(pdf, label, value)

    _heading(pdf, "State of the matter")
    briefing = data["briefing"]
    if briefing["status"] in ("ready", "stale", "failed") and briefing["text"]:
        text = briefing["text"]
        if briefing["status"] != "ready":
            text = f"(Out of date -- written before the latest changes.) {text}"
        _para(pdf, text)
    else:
        _para(pdf, _BRIEFING_PLACEHOLDER.get(briefing["status"], "Not available."))

    order = data["last_order"]
    if order is not None:
        summary = order["summary"]
        _heading(pdf, f"Last order -- {_fmt_date(order['order_date'])}")
        if summary["what_happened"]:
            _para(pdf, summary["what_happened"])
        if summary["your_side_directions"] is not None:
            sides = [
                (summary["your_side_label"], summary["your_side_directions"]),
                (summary["other_side_label"], summary["other_side_directions"]),
            ]
        else:
            sides = [
                ("Petitioner", summary["petitioner_directions"]),
                ("Respondent", summary["respondent_directions"]),
            ]
        for label, directions in sides:
            if directions:
                pdf.set_font("Helvetica", "B", 10)
                _line(pdf, f"Directions -- {label}:")
                pdf.set_font("Helvetica", "", 10)
                for direction in directions:
                    _para(pdf, f"- {direction}")

    _heading(pdf, "Open tasks and deadlines")
    if data["open_tasks"]:
        for task in data["open_tasks"]:
            due = f"due {_fmt_date(task['due_date'])}" if task["due_date"] else "no date"
            kind = "" if task["kind"] == "manual" else f" [{task['kind_display']}]"
            _para(pdf, f"- {task['title']} ({due}){kind}")
    else:
        _para(pdf, "None open.")

    _heading(pdf, "Documents on file")
    if data["documents"]:
        for document in data["documents"]:
            kind = f" ({document['document_type_display']})" if document["document_type_display"] else ""
            _para(pdf, f"- {document['filename']}{kind}")
    else:
        _para(pdf, "None uploaded.")

    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    fetched = _fmt_datetime(case["last_fetched_at"]) or "never"
    _para(
        pdf,
        f"Court tracking data as of {fetched}. Prepared "
        f"{_fmt_datetime(timezone.now())} by Case Intel from the case record -- "
        "check the court record before relying on it.",
    )

    return bytes(pdf.output())


def _hearing_text(hearing: dict) -> str:
    text = _fmt_date(hearing["hearing_date"])
    # Every eCourts hearing is typed "Other"; only a real type is worth showing.
    if hearing["hearing_type_display"] and hearing["hearing_type_display"] != "Other":
        text += f" ({hearing['hearing_type_display']})"
    return text


def _cause_list_text(cause_list: dict) -> str:
    if cause_list["status"] != "listed":
        return cause_list["status_display"] if cause_list["status"] != "not_checked" else ""
    parts = []
    if cause_list["item_number"]:
        parts.append(f"Item {cause_list['item_number']}")
    if cause_list["court_hall"]:
        parts.append(f"Court hall {cause_list['court_hall']}")
    if cause_list["stage"]:
        parts.append(cause_list["stage"])
    return ", ".join(parts) or "Listed"


def _heading(pdf, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    _line(pdf, text, height=7)
    pdf.set_font("Helvetica", "", 10)


def _fact(pdf, label: str, value: str) -> None:
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(30, 6, pdf_safe(label))
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, pdf_safe(value), new_x="LMARGIN", new_y="NEXT")


def _line(pdf, text: str, height: float = 6) -> None:
    pdf.cell(0, height, pdf_safe(text), new_x="LMARGIN", new_y="NEXT")


def _para(pdf, text: str) -> None:
    pdf.multi_cell(0, 5, pdf_safe(text), new_x="LMARGIN", new_y="NEXT")


def _fmt_date(value) -> str:
    """'12 Oct 2026' from a date, a datetime, or an ISO string."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    if isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d %b %Y")


def _fmt_datetime(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return timezone.localtime(value).strftime("%d %b %Y, %H:%M %Z")
