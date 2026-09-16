"""The shape of a hearing prep sheet.

One dict feeds both the JSON API and the PDF, so the two can't drift apart.
Directions go through build_order_summary -- the same party-aware split the
case page and calendar use -- and tasks through TaskSerializer.
"""

from __future__ import annotations

from .order_summary import build_order_summary
from .task import TaskSerializer


def serialize_hearing_digest(digest, briefing: dict) -> dict:
    hearing = digest.hearing
    case = digest.case
    snapshot = digest.snapshot or {}
    order = digest.last_order

    return {
        "hearing": {
            "id": hearing.id,
            "hearing_date": hearing.hearing_date,
            "hearing_type_display": hearing.get_hearing_type_display(),
            "status": hearing.status,
            "status_display": hearing.get_status_display(),
            "judge": hearing.judge or "",
            "location": hearing.location or "",
            "purpose": hearing.purpose or "",
            "cause_list": {
                "status": hearing.cause_list_status,
                "status_display": hearing.get_cause_list_status_display(),
                "item_number": hearing.cause_list_item_number,
                "court_hall": hearing.cause_list_court_hall,
                "stage": hearing.cause_list_stage,
                "checked_at": hearing.cause_list_checked_at,
            },
        },
        "case": {
            "id": case.id,
            "case_number": case.case_number,
            "title": case.title,
            "cnr_number": case.cnr_number,
            "court_type": case.court_type,
            "user_party_role": case.user_party_role,
            "last_fetched_at": case.last_fetched_at,
            "case_status": snapshot.get("case_status") or "",
            "case_stage": snapshot.get("case_stage") or "",
            "court_and_judge": snapshot.get("court_and_judge") or "",
        },
        "purposes": digest.purposes,
        "last_order": (
            {
                "id": order.id,
                "order_number": order.order_number,
                "order_date": order.order_date,
                "has_file": order.document_id is not None,
                "summary": build_order_summary(order),
            }
            if order is not None
            else None
        ),
        "open_tasks": TaskSerializer(digest.open_tasks, many=True).data,
        "documents": [
            {
                "id": document.id,
                "filename": document.filename,
                "document_type": document.document_type,
                "document_type_display": document.get_document_type_display()
                if document.document_type
                else "",
                "processing_status": document.processing_status,
                "document_date": document.document_date,
                "created_at": document.created_at,
            }
            for document in digest.documents
        ],
        "briefing": briefing,
    }
