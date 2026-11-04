import { addDays, format } from "date-fns";
import { isOpenTask } from "@/lib/tasks";
import type { CaseEvent, Hearing, Task } from "@/types";

/** Day keys for the calendars. A key is always "YYYY-MM-DD".
 *
 * Three kinds of date feed one calendar and each is keyed differently:
 *
 *   - a hearing is an INSTANT (eCourts stores the portal date as 00:00 UTC,
 *     a manual one can carry any time). Its day is its INDIA date, whatever
 *     timezone the browser is in -- see hearingDayKey;
 *   - a task's due_date and an event's date are plain calendar dates the
 *     advocate chose. They are keyed as-is, never round-tripped through
 *     `new Date()`/UTC, which can shift the day. */

const INDIA_DATE_PARTS = new Intl.DateTimeFormat("en-CA", {
  timeZone: "Asia/Kolkata",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** The India calendar date of a hearing's stored instant, as YYYY-MM-DD.
 *
 * 2026-11-06T00:00:00Z (an eCourts date) is 05:30 IST on the 6th; a manual
 * hearing at 00:30 IST on the 7th is 2026-11-06T19:00:00Z -- the 6th in UTC
 * and in any timezone west of India, the 7th here. Same rule the reminder
 * emails use (core/services/india_time.py). */
export function hearingDayKey(isoDateTime: string): string {
  const instant = new Date(isoDateTime);
  if (Number.isNaN(instant.getTime())) return isoDateTime.slice(0, 10);
  const parts = Object.fromEntries(
    INDIA_DATE_PARTS.formatToParts(instant).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/** A plain YYYY-MM-DD (a task's due_date, an event's date) as a day key. */
export function plainDayKey(date: string): string {
  return date.slice(0, 10);
}

/** A grid cell's local Date (built from y/m/d) as a day key. */
export function dateToDayKey(date: Date): string {
  return format(date, "yyyy-MM-dd");
}

/** A day key as a local Date at midnight, without a UTC round trip. */
export function dayKeyToDate(key: string): Date {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day);
}

// ---------------------------------------------------------------------------
// Items
// ---------------------------------------------------------------------------

export type CalendarKind = "hearing" | "task" | "event";

export const ALL_KINDS: readonly CalendarKind[] = ["hearing", "task", "event"];

export type CalendarItem =
  | { kind: "hearing"; key: string; day: string; hearing: Hearing }
  | { kind: "task"; key: string; day: string; task: Task }
  | { kind: "event"; key: string; day: string; event: CaseEvent };

export interface CalendarSources {
  hearings?: readonly Hearing[];
  tasks?: readonly Task[];
  events?: readonly CaseEvent[];
  /** Which kinds to include; all of them when omitted. */
  kinds?: ReadonlySet<CalendarKind>;
}

/** Within a day: court dates first, then appointments (all-day before
 * timed, timed by start), then deadlines. */
function sortWithinDay(a: CalendarItem, b: CalendarItem): number {
  const order: Record<CalendarKind, number> = { hearing: 0, event: 1, task: 2 };
  if (a.kind !== b.kind) return order[a.kind] - order[b.kind];
  if (a.kind === "hearing" && b.kind === "hearing") {
    return a.hearing.hearing_date.localeCompare(b.hearing.hearing_date) || a.hearing.id - b.hearing.id;
  }
  if (a.kind === "event" && b.kind === "event") {
    return (
      (a.event.start_time ?? "").localeCompare(b.event.start_time ?? "") || a.event.id - b.event.id
    );
  }
  if (a.kind === "task" && b.kind === "task") return a.task.id - b.task.id;
  return 0;
}

/** Everything that belongs on a calendar, one entry per item. A task with no
 * due date has no day, and a dismissed (cancelled) task is gone from the
 * calendar the way it is gone from the open list; a completed one stays,
 * shown as done. */
export function buildCalendarItems({
  hearings = [],
  tasks = [],
  events = [],
  kinds,
}: CalendarSources): CalendarItem[] {
  const wants = (kind: CalendarKind) => !kinds || kinds.has(kind);
  const items: CalendarItem[] = [];

  if (wants("hearing")) {
    for (const hearing of hearings) {
      items.push({
        kind: "hearing",
        key: `hearing-${hearing.id}`,
        day: hearingDayKey(hearing.hearing_date),
        hearing,
      });
    }
  }
  if (wants("task")) {
    for (const task of tasks) {
      if (!task.due_date || task.status === "cancelled") continue;
      items.push({ kind: "task", key: `task-${task.id}`, day: plainDayKey(task.due_date), task });
    }
  }
  if (wants("event")) {
    for (const event of events) {
      items.push({ kind: "event", key: `event-${event.id}`, day: plainDayKey(event.date), event });
    }
  }
  return items;
}

/** Items grouped by day key, each day in display order. */
export function bucketByDay(items: readonly CalendarItem[]): Map<string, CalendarItem[]> {
  const buckets = new Map<string, CalendarItem[]>();
  for (const item of items) {
    const list = buckets.get(item.day) ?? [];
    list.push(item);
    buckets.set(item.day, list);
  }
  for (const list of buckets.values()) list.sort(sortWithinDay);
  return buckets;
}

export function buildDayBuckets(sources: CalendarSources): Map<string, CalendarItem[]> {
  return bucketByDay(buildCalendarItems(sources));
}

/** `days` consecutive days starting at `fromKey` that have something on
 * them -- the mobile agenda. Empty days are left out. */
export function agendaDays(
  buckets: ReadonlyMap<string, CalendarItem[]>,
  fromKey: string,
  days = 30,
): { day: string; items: CalendarItem[] }[] {
  const start = dayKeyToDate(fromKey);
  const out: { day: string; items: CalendarItem[] }[] = [];
  for (let offset = 0; offset < days; offset++) {
    const day = dateToDayKey(addDays(start, offset));
    const items = buckets.get(day);
    if (items?.length) out.push({ day, items });
  }
  return out;
}

/** Counts per kind for one day's cell. Completed tasks and cancelled events
 * are not "to do", so they don't add to the markers. */
export function dayMarkerCounts(items: readonly CalendarItem[] | undefined) {
  const counts = { hearing: 0, task: 0, event: 0 };
  for (const item of items ?? []) {
    if (item.kind === "task" && !isOpenTask(item.task)) continue;
    if (item.kind === "event" && item.event.status === "cancelled") continue;
    counts[item.kind] += 1;
  }
  return counts;
}

/** "10:30:00" -> "10:30 AM". */
export function formatClock(time: string): string {
  const [hours, minutes] = time.split(":").map(Number);
  return format(new Date(2000, 0, 1, hours, minutes), "h:mm a");
}

/** "10:30 AM - 12:00 PM", "10:30 AM", or "All day". */
export function formatEventTimes(start: string | null, end: string | null): string {
  if (!start) return "All day";
  return end ? `${formatClock(start)} – ${formatClock(end)}` : formatClock(start);
}
