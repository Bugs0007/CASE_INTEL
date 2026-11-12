import type {
  PortfolioSnapshot,
  PracticeActionCard,
  PracticeCalendarEntry,
  PracticeCalendarWindow,
  PracticeReference,
  PracticeTurn,
} from "@/types/practice";

/** Typed sample data: tests use it now and wave 2 can use it for previews. */

export const FIXTURE_WEEK_START = "2026-11-09"; // a Monday
export const FIXTURE_DAY = "2026-11-11";

function ref(kind: PracticeReference["kind"], id: number, label: string, caseId: number | null = 7): PracticeReference {
  return { kind, id, case_id: caseId, label, recorded_at: null };
}

function entry(partial: Partial<PracticeCalendarEntry> & Pick<PracticeCalendarEntry, "kind" | "id" | "day" | "label">): PracticeCalendarEntry {
  return {
    case_id: 7,
    case_title: "Rao vs State",
    start_time: null,
    end_time: null,
    status: "scheduled",
    provenance: "court portal",
    needs_review: false,
    ref: ref(partial.kind, partial.id, partial.label),
    ...partial,
  };
}

export const sampleCalendar: PracticeCalendarWindow = {
  date_from: "2026-11-09",
  date_to: "2026-11-15",
  entries: [
    entry({ kind: "event", id: 20, day: "2026-11-11", label: "Mediation sitting", start_time: "15:00", end_time: "16:30" }),
    entry({ kind: "task", id: 10, day: "2026-11-11", label: "File counter affidavit", status: "pending", needs_review: true }),
    entry({ kind: "hearing", id: 1, day: "2026-11-11", label: "Hearing: for admission" }),
    entry({ kind: "task", id: 11, day: "2026-11-12", label: "Send client update", status: "completed" }),
    entry({ kind: "hearing", id: 2, day: "2026-11-12", label: "Hearing: arguments", case_id: null, case_title: null }),
  ],
  day_markers: {
    "2026-11-11": { hearing: 1, task: 1, event: 1 },
    "2026-11-12": { hearing: 1, task: 0, event: 0 },
  },
  total: 5,
  truncated: false,
  as_of: "2026-11-11T09:35:00Z",
  timezone: "Asia/Kolkata",
};

export const emptyCalendar: PracticeCalendarWindow = {
  ...sampleCalendar,
  entries: [],
  day_markers: {},
  total: 0,
};

export const samplePortfolio: PortfolioSnapshot = {
  status_counts: { open: 12, closed: 3, archived: 1 },
  total_cases: 16,
  active_cases: 12,
  active_with_next_hearing: 9,
  active_without_next_date: 3,
  cases: [
    { id: 7, title: "Rao vs State", case_number: "WP/1/2026", court: "Telangana High Court", status: "open", next_hearing_at: "2026-11-11T00:00:00Z" },
    { id: 8, title: "Sharma vs Kumar", case_number: null, court: null, status: "open", next_hearing_at: null },
  ],
  page: 1,
  page_size: 8,
  total: 16,
  as_of: "2026-11-11T09:35:00Z",
  timezone: "Asia/Kolkata",
};

export const blockedActionCard: PracticeActionCard = {
  kind: "send_invoice",
  fee_id: 31,
  case_id: 7,
  invoice_number: "INV-0007",
  amount: "15000.00",
  recipient_name: "A. Rao",
  recipient_email: null,
  blockers: ["The client has no email address on file."],
};

export const clearActionCard: PracticeActionCard = {
  ...blockedActionCard,
  recipient_email: "rao@example.com",
  blockers: [],
};

export const sampleTurn: PracticeTurn = {
  conversation_id: 1,
  user_message_id: 10,
  assistant_message_id: 11,
  answer: "You have one hearing, one deadline and one event on Wednesday.",
  intent: "calendar",
  status: "answer",
  sources: [ref("case", 7, "Rao vs State"), ref("hearing", 1, "Hearing on 11 Nov", 7), ref("fee", 31, "INV-0007", 7)],
  summary: null,
  case_candidates: [],
  action_card: null,
  as_of: "2026-11-11T09:35:00Z",
};
