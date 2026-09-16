import type { Task } from "@/types";

/** Shared date handling for tasks. A due date is a calendar DATE
 * ("2026-10-01"), so it is read as year/month/day in the viewer's own
 * calendar -- never parsed as a UTC instant, which can shift the day (see
 * formatHearingDate in lib/utils.ts for the same bug on hearings). */

const MS_PER_DAY = 86_400_000;

function localMidnight(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** Whole days from today to `isoDate`; negative when it has passed. */
export function daysUntilDate(isoDate: string): number {
  const [year, month, day] = isoDate.slice(0, 10).split("-").map(Number);
  const target = new Date(year, month - 1, day);
  return Math.round((target.getTime() - localMidnight(new Date()).getTime()) / MS_PER_DAY);
}

/** Today (+ offsetDays) as YYYY-MM-DD in the viewer's calendar. */
export function localIsoDate(offsetDays = 0): string {
  const date = localMidnight(new Date());
  date.setDate(date.getDate() + offsetDays);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function dueLabel(days: number): string {
  if (days < -1) return `${-days} days overdue`;
  if (days === -1) return "1 day overdue";
  if (days === 0) return "Due today";
  if (days === 1) return "Due tomorrow";
  return `Due in ${days} days`;
}

/** Chip colour meaning: alert when overdue, pending within a week. */
export function dueChipVariant(days: number): "ok" | "pending" | "alert" | "none" {
  if (days < 0) return "alert";
  if (days <= 7) return "pending";
  return "none";
}

export function isOpenTask(task: Task): boolean {
  return task.status === "pending" || task.status === "in_progress";
}

/** Short, honest note on where a generated date came from. */
export const DUE_DATE_BASIS_NOTE: Record<Task["due_date_basis"], string | null> = {
  "": null,
  explicit_date: "date stated in the order",
  relative_to_order: "counted from the order date",
  next_hearing_fallback: "no period stated — using the next hearing",
  limitation_rule: "computed from a limitation rule — verify",
};
