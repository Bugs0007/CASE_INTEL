"""Assemble a hearing's prep sheet from rows already in the database.

Pure composition: no LLM, no portal, no writes. Cheap enough to run on
every view.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import CourtOrder, Document, Hearing, Task
from core.services.court_tracking import latest_snapshot

# An order with a resolved overview. Pending and failed ones have nothing
# to show yet.
RESOLVED_SUMMARY_STATUSES = (
    CourtOrder.SUMMARY_SUMMARIZED,
    CourtOrder.SUMMARY_NO_DIRECTIONS,
    CourtOrder.SUMMARY_UNREADABLE,
)


@dataclass
class HearingDigest:
    hearing: Hearing
    last_order: CourtOrder | None
    open_tasks: list[Task]
    documents: list[Document]
    # What the hearing is for, most specific first, without repeats.
    purposes: list[str]
    # Latest eCourts snapshot (case status/stage/court), or None.
    snapshot: dict | None

    @property
    def case(self):
        return self.hearing.case


def assemble_hearing_digest(hearing: Hearing) -> HearingDigest:
    case = hearing.case
    hearing_day = hearing.hearing_date.date()

    last_order = (
        CourtOrder.objects.filter(
            case=case,
            order_date__lt=hearing_day,
            summary_status__in=RESOLVED_SUMMARY_STATUSES,
        )
        .select_related("case", "document")
        .order_by("-order_date", "-created_at")
        .first()
    )

    open_tasks = list(
        Task.objects.filter(case=case, status__in=Task.OPEN_STATUSES)
        .select_related("case")
        .order_by("due_date", "created_at")
    )

    documents = list(
        Document.objects.filter(case=case)
        .exclude(document_type="court_order")
        .order_by("-created_at")
    )

    purposes: list[str] = []
    if last_order and last_order.summary_next_date == hearing_day:
        purposes.append(last_order.summary_next_date_purpose)
    purposes.append(hearing.purpose or "")
    purposes = list(dict.fromkeys(p.strip() for p in purposes if p and p.strip()))

    return HearingDigest(
        hearing=hearing,
        last_order=last_order,
        open_tasks=open_tasks,
        documents=documents,
        purposes=purposes,
        snapshot=latest_snapshot(case),
    )
