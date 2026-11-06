import { hearingDayKey } from "@/lib/calendar";

/** Date helpers for the dashboard. Plain TypeScript, no React.
 *
 * Everything here is a calendar DATE ("YYYY-MM-DD", "a day key") in
 * India. Day keys are read as year/month/day and offset with local
 * getters -- never round-tripped through toISOString().slice(0, 10), which
 * moves the day for anyone east or west of UTC (IST is +05:30, so
 * 00:30 IST on the 6th is still the 5th in UTC). The one place an instant
 * becomes a day is `istDayKey`, which asks for the Asia/Kolkata date. */

const MS_PER_DAY = 86_400_000;

const WEEKDAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEKDAYS_LONG = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** The India calendar date of an instant. */
export function istDayKey(now: Date = new Date()): string {
  return hearingDayKey(now.toISOString());
}

function parts(key: string): [number, number, number] {
  const [year, month, day] = key.slice(0, 10).split("-").map(Number);
  return [year, month, day];
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** A day key as a local Date at midnight. */
export function dayKeyToDate(key: string): Date {
  const [year, month, day] = parts(key);
  return new Date(year, month - 1, day);
}

/** A local Date as a day key, read with local getters. */
export function dateToDayKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** `key` moved by `offset` calendar days (negative = earlier). */
export function addDays(key: string, offset: number): string {
  const [year, month, day] = parts(key);
  return dateToDayKey(new Date(year, month - 1, day + offset));
}

/** Whole days from `from` to `to`; negative when `to` is earlier. Counted
 * on UTC midnights so a daylight-saving change can't make a day 23 or 25
 * hours long. */
export function daysBetween(from: string, to: string): number {
  const [fy, fm, fd] = parts(from);
  const [ty, tm, td] = parts(to);
  return Math.round((Date.UTC(ty, tm - 1, td) - Date.UTC(fy, fm - 1, fd)) / MS_PER_DAY);
}

/** "Fri 6 Nov". */
export function shortDay(key: string): string {
  const date = dayKeyToDate(key);
  return `${WEEKDAYS_SHORT[date.getDay()]} ${date.getDate()} ${MONTHS_SHORT[date.getMonth()]}`;
}

/** "6 Nov". */
export function dayMonth(key: string): string {
  const date = dayKeyToDate(key);
  return `${date.getDate()} ${MONTHS_SHORT[date.getMonth()]}`;
}

/** "Today", "Tomorrow", otherwise "Fri 6 Nov". */
export function dateLabel(key: string, today: string): string {
  const diff = daysBetween(today, key);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return shortDay(key);
}

/** "Thursday, 5 November 2026". */
export function longDate(key: string): string {
  const date = dayKeyToDate(key);
  return `${WEEKDAYS_LONG[date.getDay()]}, ${date.getDate()} ${MONTHS_LONG[date.getMonth()]} ${date.getFullYear()}`;
}

/** "Good morning" before 12:00, "Good afternoon" before 17:00, else
 * "Good evening". `hour` is the viewer's local hour (0-23). */
export function greetingFor(hour: number): string {
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}
