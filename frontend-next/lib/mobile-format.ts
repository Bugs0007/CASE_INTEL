import { dayKeyToDate, daysBetween } from "@/lib/dashboard/dates";

/** Wording for the phone layouts, as plain functions so it can be tested.
 * Days are India day keys ("YYYY-MM-DD"). */

const WEEKDAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];

export interface DateTile {
  weekday: string;
  date: string;
  month: string;
}

/** The three lines of a date tile: "FRI" / "6" / "NOV". */
export function dateTile(day: string): DateTile {
  const d = dayKeyToDate(day);
  return { weekday: WEEKDAYS[d.getDay()], date: String(d.getDate()), month: MONTHS[d.getMonth()] };
}

/** How far a day is from today, in words: "Today", "Tomorrow", "In 5 days",
 * "Yesterday", "3 days ago"; past two weeks either way it is the date. */
export function relativeDay(day: string, today: string): string {
  const diff = daysBetween(today, day);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  if (diff > 1 && diff <= 14) return `In ${diff} days`;
  if (diff < -1 && diff >= -14) return `${-diff} days ago`;
  const d = dayKeyToDate(day);
  return `${d.getDate()} ${MONTHS[d.getMonth()].charAt(0)}${MONTHS[d.getMonth()].slice(1).toLowerCase()}`;
}

export type Urgency = "alert" | "pending" | "none";

/** How loudly a due date should speak: overdue is red, within two days is
 * amber, anything later is quiet. No date is quiet. */
export function dueUrgency(due: string | null, today: string): Urgency {
  if (!due) return "none";
  const diff = daysBetween(today, due);
  if (diff < 0) return "alert";
  if (diff <= 2) return "pending";
  return "none";
}

/** "2 days overdue" / "Due today" / "Due tomorrow" / "Due in 6 days" / "". */
export function dueWords(due: string | null, today: string): string {
  if (!due) return "";
  const diff = daysBetween(today, due);
  if (diff < 0) return `${-diff} ${diff === -1 ? "day" : "days"} overdue`;
  if (diff === 0) return "Due today";
  if (diff === 1) return "Due tomorrow";
  return `Due in ${diff} days`;
}

/** "Rs 15,000" style amounts are formatted elsewhere (formatINR); this is the
 * compact form for a tight chip: 15000 -> "15K", 2,40,000 -> "2.4L",
 * 1,20,00,000 -> "1.2Cr" (the Indian grouping a lawyer reads). */
export function compactINR(value: string | number): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "";
  const abs = Math.abs(n);
  const trim = (x: number) => String(Math.round(x * 10) / 10).replace(/\.0$/, "");
  if (abs >= 1e7) return `${trim(n / 1e7)}Cr`;
  if (abs >= 1e5) return `${trim(n / 1e5)}L`;
  if (abs >= 1e3) return `${trim(n / 1e3)}K`;
  return String(Math.round(n));
}
