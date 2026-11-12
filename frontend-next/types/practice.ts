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
  | "propose_invoice_send";
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
  action_card: PracticeActionCard | null;
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
