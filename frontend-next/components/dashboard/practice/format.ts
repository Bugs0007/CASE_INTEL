import { addDays, format } from "date-fns";
import { dateToDayKey, dayKeyToDate, hearingDayKey } from "@/lib/calendar";

/** Today's India day key, from the same rule the calendars use. */
export function todayDayKey(): string {
  return hearingDayKey(new Date().toISOString());
}

export function addDaysToKey(key: string, days: number): string {
  return dateToDayKey(addDays(dayKeyToDate(key), days));
}

/** The Monday of the week that holds `key`. */
export function weekStartOf(key: string): string {
  const weekday = dayKeyToDate(key).getDay(); // 0 = Sunday
  return addDaysToKey(key, -((weekday + 6) % 7));
}

export function weekDayKeys(weekStart: string): string[] {
  return Array.from({ length: 7 }, (_, offset) => addDaysToKey(weekStart, offset));
}

export function formatDayLong(key: string): string {
  return format(dayKeyToDate(key), "EEEE d MMMM");
}

export function formatWeekRange(weekStart: string): string {
  const start = dayKeyToDate(weekStart);
  const end = dayKeyToDate(addDaysToKey(weekStart, 6));
  return `${format(start, "d MMM")} to ${format(end, "d MMM yyyy")}`;
}

const AS_OF_PARTS = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

/** "3:05 pm" in India time, or "" when the stamp is not a date. */
export function formatAsOf(iso: string): string {
  const instant = new Date(iso);
  return Number.isNaN(instant.getTime()) ? "" : AS_OF_PARTS.format(instant);
}

/** A hearing instant as "6 Nov 2026" on its India day. */
export function formatHearingDay(iso: string): string {
  return format(dayKeyToDate(hearingDayKey(iso)), "d MMM yyyy");
}

export function humanize(value: string): string {
  const text = value.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
