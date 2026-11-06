import { hearingDayKey } from "@/lib/calendar";
import { addDays, dayKeyToDate, daysBetween } from "@/lib/dashboard/dates";
import type { CalendarItem } from "@/lib/calendar";
import { primaryClientContact } from "@/lib/utils";
import type { Case, CourtOrder, Hearing } from "@/types";

/** What the case page's compact cards show, as plain functions of the data so
 * the row counts and the wording can be tested without rendering anything. */

export type HearingTone = "upcoming" | "passed" | "order" | "other";

export interface HearingRow {
  hearing: Hearing;
  /** India date of the hearing, YYYY-MM-DD. */
  day: string;
  tone: HearingTone;
  /** The status word at the right edge: UPCOMING, PASSED, ORDER PASSED... */
  status: string;
  /** One line about it: the cause-list state, the outcome, the purpose. */
  text: string;
  /** The first saved order filed on this hearing's date, if any. */
  order: CourtOrder | null;
  /** The next hearing: drawn on a pale gold row. */
  isNext: boolean;
}

function ordersByDay(orders: readonly CourtOrder[]): Map<string, CourtOrder[]> {
  const by = new Map<string, CourtOrder[]>();
  for (const order of orders) {
    if (!order.order_date) continue;
    by.set(order.order_date, [...(by.get(order.order_date) ?? []), order]);
  }
  return by;
}

function textFor(h: Hearing, isUpcoming: boolean): string {
  if (isUpcoming) {
    switch (h.cause_list_status) {
      case "not_published":
        return "Cause list not published yet";
      case "listed": {
        const where = [
          h.cause_list_item_number && `Item ${h.cause_list_item_number}`,
          h.cause_list_court_hall && `Court ${h.cause_list_court_hall}`,
        ].filter(Boolean);
        return where.length ? `Listed · ${where.join(" · ")}` : "Listed";
      }
      case "not_listed":
        return "Not on the published cause list";
      case "fetch_failed":
        return "Couldn't check the cause list";
      case "unsupported":
        return h.purpose || h.hearing_type_display || "Cause list not covered for this court";
      default:
        break;
    }
  }
  return h.outcome || h.purpose || h.notes || h.hearing_type_display || "";
}

/** One hearing as a row. `today` is the India date. */
export function toHearingRow(
  h: Hearing,
  orders: ReadonlyMap<string, CourtOrder[]>,
  today: string,
  isNext = false,
): HearingRow {
  const day = hearingDayKey(h.hearing_date);
  const order = (orders.get(day) ?? []).find((o) => o.has_file) ?? orders.get(day)?.[0] ?? null;
  const isUpcoming = h.status === "scheduled" && day >= today;

  let tone: HearingTone = "passed";
  let status = "PASSED";
  if (isUpcoming) {
    tone = "upcoming";
    status = "UPCOMING";
  } else if (h.status === "scheduled") {
    tone = "other";
    status = "AWAITING UPDATE";
  } else if (h.status === "cancelled") {
    tone = "other";
    status = "CANCELLED";
  } else if (h.status === "postponed") {
    tone = "other";
    status = "POSTPONED";
  }
  if (order && !isUpcoming && tone !== "other") {
    tone = "order";
    status = "ORDER PASSED";
  }
  return { hearing: h, day, tone, status, text: textFor(h, isUpcoming), order, isNext };
}

/** Every hearing as a row: the next one first, then the most recent. */
export function allHearingRows(
  hearings: readonly Hearing[],
  orders: readonly CourtOrder[],
  today: string,
): HearingRow[] {
  const by = ordersByDay(orders);
  const upcoming = hearings
    .filter((h) => h.status === "scheduled" && hearingDayKey(h.hearing_date) >= today)
    .sort((a, b) => a.hearing_date.localeCompare(b.hearing_date) || a.id - b.id);
  const nextId = upcoming[0]?.id;
  const rest = hearings
    .filter((h) => !upcoming.includes(h))
    .sort((a, b) => b.hearing_date.localeCompare(a.hearing_date) || b.id - a.id);
  // Upcoming ones after the first follow it, soonest first.
  return [...upcoming, ...rest].map((h) => toHearingRow(h, by, today, h.id === nextId));
}

/** The card's rows: exactly `count` of them (or fewer when there are fewer
 * hearings): the next hearing, then the most recent ones. */
export function compactHearingRows(
  hearings: readonly Hearing[],
  orders: readonly CourtOrder[],
  today: string,
  count: number,
): { rows: HearingRow[]; total: number } {
  const all = allHearingRows(hearings, orders, today);
  return { rows: all.slice(0, Math.max(0, count)), total: all.length };
}

export type HearingFilter = "all" | "upcoming" | "passed" | "orders";

export function filterHearingRows(rows: readonly HearingRow[], filter: HearingFilter): HearingRow[] {
  switch (filter) {
    case "upcoming":
      return rows.filter((r) => r.tone === "upcoming");
    case "passed":
      return rows.filter((r) => r.tone !== "upcoming");
    case "orders":
      return rows.filter((r) => r.order !== null);
    default:
      return [...rows];
  }
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

export interface MiniDay {
  day: string;
  /** In the month of `today`. */
  inMonth: boolean;
  isToday: boolean;
}

/** Five rows of the month containing `today`, Sunday first. A month that
 * would need six rows starts a week later so `today` is always on show. */
export function miniMonthWeeks(today: string): MiniDay[][] {
  const first = `${today.slice(0, 8)}01`;
  const firstDay = dayKeyToDate(first);
  let start = addDays(first, -firstDay.getDay());
  if (daysBetween(start, today) >= 35) start = addDays(start, 7);
  const month = today.slice(0, 7);
  return Array.from({ length: 5 }, (_, week) =>
    Array.from({ length: 7 }, (_, d) => {
      const day = addDays(start, week * 7 + d);
      return { day, inMonth: day.startsWith(month), isToday: day === today };
    }),
  );
}

/** The seven days of the week containing `today`, Monday first. */
export function weekStrip(today: string): MiniDay[] {
  const dow = (dayKeyToDate(today).getDay() + 6) % 7; // Monday = 0
  const start = addDays(today, -dow);
  return Array.from({ length: 7 }, (_, d) => {
    const day = addDays(start, d);
    return { day, inMonth: true, isToday: day === today };
  });
}

export interface ComingUpRow {
  day: string;
  kind: CalendarItem["kind"];
  text: string;
}

/** The next `count` hearings, events and deadlines from today on. */
export function comingUpRows(
  buckets: ReadonlyMap<string, CalendarItem[]>,
  today: string,
  count: number,
): ComingUpRow[] {
  const rows: ComingUpRow[] = [];
  const days = [...buckets.keys()].filter((d) => d >= today).sort();
  for (const day of days) {
    for (const item of buckets.get(day) ?? []) {
      if (item.kind === "task" && (item.task.status === "completed" || item.task.status === "cancelled")) continue;
      if (item.kind === "event" && item.event.status === "cancelled") continue;
      const text =
        item.kind === "hearing"
          ? `Hearing${item.hearing.location ? ` · ${item.hearing.location}` : ""}`
          : item.kind === "task"
            ? `Task · ${item.task.title}`
            : item.event.title;
      rows.push({ day, kind: item.kind, text });
      if (rows.length >= count) return rows;
    }
  }
  return rows;
}

// ---------------------------------------------------------------------------
// Header and facts
// ---------------------------------------------------------------------------

/** "just now", "5m ago", "2h ago", "3d ago". */
export function agoShort(iso: string, now: number = Date.now()): string {
  const ms = now - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export type SyncTone = "ok" | "stale" | "failed" | "off";

/** The court-tracking sync status in the header: what it says and its dot. */
export function syncState(
  c: Pick<Case, "tracking_enabled" | "fetch_status" | "last_fetched_at" | "tracking_freshness">,
  now: number = Date.now(),
): { label: string; tone: SyncTone } {
  if (!c.tracking_enabled) return { label: "Court tracking off", tone: "off" };
  if (c.fetch_status === "failed") return { label: "Court tracking failed", tone: "failed" };
  if (!c.last_fetched_at) return { label: "Court tracking not synced yet", tone: "stale" };
  return {
    label: `Court tracking synced ${agoShort(c.last_fetched_at, now)}`,
    tone: c.tracking_freshness?.stale ? "stale" : "ok",
  };
}

export interface CaseFacts {
  court: string;
  stage: string;
  /** "" when the side is not set. */
  side: string;
  client: string;
  /** YYYY-MM-DD, or "" when unknown. */
  filed: string;
  cnr: string;
}

export function caseFacts(c: Case): CaseFacts {
  const snap = c.tracking_snapshot;
  const contact = primaryClientContact(c.client_contacts ?? []);
  return {
    court: snap?.court_name || snap?.court_and_judge || "—",
    stage: snap?.case_stage || snap?.case_status || "—",
    side: c.user_party_role === "petitioner" ? "Petitioner" : c.user_party_role === "respondent" ? "Respondent" : "",
    client: c.client_detail?.name || contact?.name || c.client_name || "—",
    filed: c.filing_date ? c.filing_date.slice(0, 10) : "",
    cnr: c.cnr_number || "—",
  };
}
