// Mirrors core/serializers/case_event.py (CaseEventSerializer).

export type CaseEventType =
  | "arbitration"
  | "mediation"
  | "client_meeting"
  | "client_call"
  | "internal_meeting"
  | "site_visit"
  | "filing"
  | "other";

export type CaseEventStatus = "scheduled" | "completed" | "cancelled";

/** An appointment the advocate put on a case's calendar. Not a hearing (a
 * court date) and not a task (a due date). */
export interface CaseEvent {
  id: number;
  case: number;
  case_title: string;
  case_number: string;
  title: string;
  event_type: CaseEventType;
  event_type_display: string;
  /** India calendar date, YYYY-MM-DD. */
  date: string;
  /** India local time, "HH:MM:SS". Null means all-day. */
  start_time: string | null;
  end_time: string | null;
  /** An address or a meeting link. */
  location: string;
  notes: string;
  status: CaseEventStatus;
  created_at: string;
  updated_at: string;
}

/** Writable fields. */
export interface CaseEventInput {
  case: number;
  title: string;
  event_type?: CaseEventType;
  date: string;
  start_time?: string | null;
  end_time?: string | null;
  location?: string;
  notes?: string;
  status?: CaseEventStatus;
}

export interface CaseEventFilters {
  case_id?: number;
  /** YYYY-MM-DD, inclusive. */
  date_from?: string;
  /** YYYY-MM-DD, inclusive. */
  date_to?: string;
  status?: CaseEventStatus;
}
