/**
 * Shapes for the dashboard practice assistant and compact calendar.
 * Mirror of core/services/practice_assistant/contracts.py. Change both together.
 */

export type RefKind = "case" | "hearing" | "task" | "event" | "document" | "fee";
export type PracticeCalendarKind = "hearing" | "task" | "event";
export type PracticeIntent =
  | "overview"
  | "calendar"
  | "open_deadlines"
  | "missing_next_date"
  | "case_facts"
  | "billing_summary"
  | "propose_invoice_send"
  | "propose_fee_create"
  | "propose_fee_update"
  | "propose_invoice_generate"
  | "propose_fee_delete"
  | "practice_report"
  | "propose_draft"
  | "compare"
  | "today_focus"
  | "attention"
  | "propose_task"
  | "propose_mark_paid"
  | "propose_bulk_fees"
  | "propose_bulk_send";
export type PracticeTurnStatus = "answer" | "needs_clarification" | "partial";

/** A pointer to one owned record. Build links from `kind`, never from text. */
export interface PracticeReference {
  kind: RefKind;
  id: number;
  case_id: number | null;
  label: string;
  recorded_at: string | null;
}

export interface PracticeCalendarEntry {
  kind: PracticeCalendarKind;
  id: number;
  case_id: number | null;
  case_title: string | null;
  /** India day key, YYYY-MM-DD */
  day: string;
  /** HH:MM India time; null = all day or untimed */
  start_time: string | null;
  end_time: string | null;
  status: string;
  label: string;
  provenance: string;
  needs_review: boolean;
  ref: PracticeReference;
}

export interface PracticeDayMarkers {
  hearing: number;
  task: number;
  event: number;
}

export interface PracticeCalendarWindow {
  date_from: string;
  /** inclusive */
  date_to: string;
  entries: PracticeCalendarEntry[];
  day_markers: Record<string, PracticeDayMarkers>;
  total: number;
  truncated: boolean;
  as_of: string;
  timezone: string;
}

export interface PracticeCaseRow {
  id: number;
  title: string;
  case_number: string | null;
  court: string | null;
  status: string;
  next_hearing_at: string | null;
}

export interface PortfolioSnapshot {
  status_counts: Record<string, number>;
  total_cases: number;
  active_cases: number;
  active_with_next_hearing: number;
  active_without_next_date: number;
  cases: PracticeCaseRow[];
  page: number;
  page_size: number;
  /** rows matching the case filter, not cases.length */
  total: number;
  as_of: string;
  timezone: string;
}

export interface PracticeCaseCandidate {
  id: number;
  title: string;
  case_number: string | null;
  court: string | null;
}

/** A proposed action the advocate must confirm. Built from server data only. */
export interface PracticeActionCard {
  kind: "send_invoice";
  fee_id: number;
  case_id: number;
  invoice_number: string | null;
  amount: string;
  recipient_name: string | null;
  recipient_email: string | null;
  /** non-empty = cannot be confirmed */
  blockers: string[];
}

export type PracticeFeeCategory = "appearance" | "hotel" | "flight" | "other";

interface PracticeCardBase {
  case_id: number;
  case_title: string;
  /** non-empty = cannot be confirmed */
  blockers: string[];
}

export interface PracticeCreateFeeCard extends PracticeCardBase {
  kind: "create_fee";
  hearing_id: number | null;
  hearing_options: { id: number; label: string; date: string }[];
  category: PracticeFeeCategory;
  /** null = use the profile default (appearance only) */
  amount: string | null;
  description: string;
}

export interface PracticeFeeFields {
  amount?: string;
  category?: PracticeFeeCategory;
  description?: string;
}

export interface PracticeUpdateFeeCard extends PracticeCardBase {
  kind: "update_fee";
  fee_id: number;
  invoice_number: string | null;
  fee_status: string;
  current: { amount: string; category: PracticeFeeCategory; description: string };
  /** only the fields that change */
  proposed: PracticeFeeFields;
  regenerates_invoice: boolean;
}

export interface PracticeGenerateInvoiceCard extends PracticeCardBase {
  kind: "generate_invoice";
  fee_id: number;
  amount: string;
  category: PracticeFeeCategory;
}

export interface PracticeDeleteFeeCard extends PracticeCardBase {
  kind: "delete_fee";
  fee_id: number;
  amount: string;
  category: PracticeFeeCategory;
  fee_status: string;
}

export type PracticeDraftSubtype = "status_memo" | "personal_note" | "client_letter" | "list_of_dates";

export interface PracticeStartDraftCard extends PracticeCardBase {
  kind: "start_draft";
  subtype: PracticeDraftSubtype;
  subtype_label: string;
  instructions: string;
}

export interface PracticeCreateTaskCard {
  kind: "create_task";
  /** null = a task on no case */
  case_id: number | null;
  case_title: string;
  title: string;
  due_date: string | null;
  blockers: string[];
}

export interface PracticeMarkPaidCard extends PracticeCardBase {
  kind: "mark_invoice_paid";
  fee_id: number;
  invoice_number: string | null;
  amount: string;
  category: PracticeFeeCategory;
  fee_status: string;
}

export interface PracticeBulkCreateFeesCard {
  kind: "bulk_create_fees";
  case_id: null;
  case_title: string;
  category: PracticeFeeCategory;
  /** null = the profile default */
  amount: string | null;
  period_text: string;
  rows: { hearing_id: number; case_id: number; case_title: string; date: string; label: string }[];
  blockers: string[];
}

export interface PracticeBulkSendInvoicesCard {
  kind: "bulk_send_invoices";
  case_id: null;
  case_title: string;
  rows: {
    fee_id: number;
    case_id: number;
    case_title: string;
    invoice_number: string | null;
    amount: string;
    recipient_email: string | null;
    blockers: string[];
  }[];
  blockers: string[];
}

/** Every card the assistant can propose. Each is only a proposal. */
export type PracticeAnyActionCard =
  | PracticeActionCard
  | PracticeCreateFeeCard
  | PracticeUpdateFeeCard
  | PracticeGenerateInvoiceCard
  | PracticeDeleteFeeCard
  | PracticeStartDraftCard
  | PracticeCreateTaskCard
  | PracticeMarkPaidCard
  | PracticeBulkCreateFeesCard
  | PracticeBulkSendInvoicesCard;

export type PracticeReportKind = "billing" | "hearings" | "cases" | "deadlines" | "brief";
export type PracticeReportFormat = "pdf" | "docx";

/** A report the server built from the advocate's data. Files are fetched
 * from the fields here, never from a URL in the response. */
export interface PracticeReportCard {
  kind: PracticeReportKind;
  title: string;
  date_from: string | null;
  date_to: string | null;
  row_count: number;
  formats: PracticeReportFormat[];
  /** Hearings (brief only) whose "state of the matter" paragraph is not written yet. */
  briefings_missing?: number[];
}

export interface PracticeTurn {
  conversation_id: number;
  user_message_id: number;
  assistant_message_id: number;
  answer: string;
  intent: PracticeIntent | null;
  status: PracticeTurnStatus;
  sources: PracticeReference[];
  summary: Record<string, unknown> | null;
  case_candidates: PracticeCaseCandidate[];
  action_card: PracticeAnyActionCard | null;
  report?: PracticeReportCard | null;
  as_of: string;
}

/** GET /api/practice-assistant/overview/?from=YYYY-MM-DD&to=YYYY-MM-DD */
export interface PracticeOverview {
  portfolio: PortfolioSnapshot;
  calendar: PracticeCalendarWindow;
}

/** POST /api/practice-assistant/chat/ */
export interface PracticeChatRequest {
  query: string;
  conversation_id?: number;
  selected_day?: string;
  /** A case the advocate picked from the chooser. The server verifies ownership. */
  case_id?: number;
  client_request_id: string;
}
