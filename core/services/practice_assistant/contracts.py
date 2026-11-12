"""Shapes shared by the practice read model, the practice graph and the API.

The frontend mirror is frontend-next/types/practice.ts. Change both together.
Every read takes the owner as a required keyword argument and a `scope`;
"personal" is the only scope today (firm scope arrives with the firm track).
"""
from typing import Literal, Optional, TypedDict

SCOPE_PERSONAL = "personal"

DEFAULT_RANGE_DAYS = 7
MAX_RANGE_DAYS = 31
PAGE_SIZE = 25
HARD_ROW_CAP = 100
TIMEZONE = "Asia/Kolkata"

RefKind = Literal["case", "hearing", "task", "event", "document", "fee"]
CalendarKind = Literal["hearing", "task", "event"]
Intent = Literal[
    "overview",
    "calendar",
    "open_deadlines",
    "missing_next_date",
    "case_facts",
    "billing_summary",
    "propose_invoice_send",
    "propose_fee_create",
    "propose_fee_update",
    "propose_invoice_generate",
    "propose_fee_delete",
    "practice_report",
    "propose_draft",
]
INTENTS: tuple[str, ...] = (
    "overview",
    "calendar",
    "open_deadlines",
    "missing_next_date",
    "case_facts",
    "billing_summary",
    "propose_invoice_send",
    "propose_fee_create",
    "propose_fee_update",
    "propose_invoice_generate",
    "propose_fee_delete",
    "practice_report",
    "propose_draft",
)
TurnStatus = Literal["answer", "needs_clarification", "partial"]


class Reference(TypedDict):
    """A pointer to one owned record. Links are built client-side from `kind`."""

    kind: RefKind
    id: int
    case_id: Optional[int]
    label: str
    recorded_at: Optional[str]  # ISO 8601 with offset, or a plain YYYY-MM-DD


class CalendarEntry(TypedDict):
    kind: CalendarKind
    id: int
    case_id: Optional[int]
    case_title: Optional[str]
    day: str  # India day key, YYYY-MM-DD
    start_time: Optional[str]  # HH:MM India time; None = all day / untimed
    end_time: Optional[str]
    status: str  # the record's own status value
    label: str
    provenance: str  # hearing: ecourts|manual; task: manual|order_direction|limitation; event: manual
    needs_review: bool
    ref: Reference


class DayMarkers(TypedDict):
    hearing: int
    task: int
    event: int


class CalendarWindow(TypedDict):
    date_from: str
    date_to: str  # inclusive
    entries: list[CalendarEntry]
    day_markers: dict[str, DayMarkers]
    total: int
    truncated: bool
    as_of: str
    timezone: str


class CaseRow(TypedDict):
    id: int
    title: str
    case_number: Optional[str]
    court: Optional[str]
    status: str
    next_hearing_at: Optional[str]


class PortfolioSnapshot(TypedDict):
    status_counts: dict[str, int]
    total_cases: int
    active_cases: int
    active_with_next_hearing: int
    active_without_next_date: int
    cases: list[CaseRow]
    page: int
    page_size: int
    total: int  # rows matching the case filter, not len(cases)
    as_of: str
    timezone: str


class DeadlineRow(TypedDict):
    id: int
    case_id: Optional[int]
    case_title: Optional[str]
    title: str
    due_date: Optional[str]
    status: str
    kind: str  # manual | order_direction | limitation
    needs_review: bool
    due_date_basis: Optional[str]
    overdue: bool
    ref: Reference


class OpenDeadlines(TypedDict):
    entries: list[DeadlineRow]
    total: int
    truncated: bool
    as_of: str
    timezone: str


class CaseCandidate(TypedDict):
    id: int
    title: str
    case_number: Optional[str]
    court: Optional[str]


class SendInvoiceCard(TypedDict):
    """Confirm: the existing send endpoint. Built from server data only."""

    kind: Literal["send_invoice"]
    fee_id: int
    case_id: int
    case_title: str
    invoice_number: Optional[str]
    amount: str  # decimal as a string
    recipient_name: Optional[str]
    recipient_email: Optional[str]
    blockers: list[str]  # non-empty = cannot be confirmed


class HearingOption(TypedDict):
    id: int
    label: str
    date: str  # India date, YYYY-MM-DD


class CreateFeeCard(TypedDict):
    """Confirm: POST /api/appearance-fees/ {hearing, category, amount?, notes}."""

    kind: Literal["create_fee"]
    case_id: int
    case_title: str
    hearing_id: Optional[int]
    hearing_options: list[HearingOption]
    category: str
    amount: Optional[str]  # None = the profile default (appearance only)
    description: str
    blockers: list[str]


class FeeFields(TypedDict, total=False):
    amount: str
    category: str
    description: str


class UpdateFeeCard(TypedDict):
    """Confirm: PATCH /api/appearance-fees/<fee_id>/ with `proposed`."""

    kind: Literal["update_fee"]
    case_id: int
    case_title: str
    fee_id: int
    invoice_number: Optional[str]
    fee_status: str
    current: FeeFields
    proposed: FeeFields  # only the fields that change
    regenerates_invoice: bool
    blockers: list[str]


class GenerateInvoiceCard(TypedDict):
    """Confirm: POST /api/appearance-fees/<fee_id>/invoice/."""

    kind: Literal["generate_invoice"]
    case_id: int
    case_title: str
    fee_id: int
    amount: str
    category: str
    blockers: list[str]


class DeleteFeeCard(TypedDict):
    """Confirm: DELETE /api/appearance-fees/<fee_id>/."""

    kind: Literal["delete_fee"]
    case_id: int
    case_title: str
    fee_id: int
    amount: str
    category: str
    fee_status: str
    blockers: list[str]


class StartDraftCard(TypedDict):
    """Confirm: POST /api/case-assistant/drafts/ (the drafting studio's
    payload), then link to that draft in the drafting UI."""

    kind: Literal["start_draft"]
    case_id: int
    case_title: str
    subtype: str
    subtype_label: str
    instructions: str
    blockers: list[str]


ActionCard = (
    SendInvoiceCard
    | CreateFeeCard
    | UpdateFeeCard
    | GenerateInvoiceCard
    | DeleteFeeCard
    | StartDraftCard
)

ReportKind = Literal["billing", "hearings", "cases", "deadlines"]
REPORT_KINDS: tuple[str, ...] = ("billing", "hearings", "cases", "deadlines")
REPORT_FORMATS: tuple[str, ...] = ("pdf", "docx")


class ReportCard(TypedDict):
    """A report the advocate can download. The file is
    GET /api/practice-assistant/reports/<kind>/<fmt>/?date_from=&date_to=,
    built by the client from these fields (never from a URL in a response)."""

    kind: ReportKind
    title: str
    date_from: Optional[str]
    date_to: Optional[str]
    row_count: int
    formats: list[str]


class PracticeTurn(TypedDict):
    conversation_id: int
    user_message_id: int
    assistant_message_id: int
    answer: str
    intent: Optional[Intent]
    status: TurnStatus
    sources: list[Reference]
    summary: Optional[dict]  # the structured read result the answer was built from
    case_candidates: list[CaseCandidate]
    action_card: Optional[ActionCard]
    report: Optional[ReportCard]
    as_of: str
