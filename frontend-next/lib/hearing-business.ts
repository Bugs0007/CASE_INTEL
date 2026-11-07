import { APIError, apiErrorDetail } from "@/lib/api/client";
import { hearingDayKey, plainDayKey } from "@/lib/calendar";
import type { DailyStatusEntry } from "@/types/daily-status";
import type { Hearing } from "@/types";

/** What the court recorded at each hearing (the District Courts "Daily
 * Status" entries), matched to the hearings by DAY.
 *
 * A hearing's business is the entry whose business_date is the hearing's
 * India calendar date. Entry dates are plain "YYYY-MM-DD" and are only ever
 * compared as strings: never through `new Date(iso)`, which can shift the
 * day. The hearing's own date is an instant, so it goes through
 * hearingDayKey (its India date). */

/** The entries keyed by their plain date. A date never has two entries (the
 * server stores one per case and date); if one ever did, the first (newest
 * fetched) wins. */
export function indexBusinessByDate(
  entries: readonly DailyStatusEntry[] | undefined,
): Map<string, DailyStatusEntry> {
  const byDate = new Map<string, DailyStatusEntry>();
  for (const entry of entries ?? []) {
    const key = plainDayKey(entry.business_date);
    if (!byDate.has(key)) byDate.set(key, entry);
  }
  return byDate;
}

/** The entry recorded on a hearing's day, or undefined. */
export function businessForHearing(
  index: ReadonlyMap<string, DailyStatusEntry>,
  hearing: Pick<Hearing, "hearing_date">,
): DailyStatusEntry | undefined {
  return index.get(hearingDayKey(hearing.hearing_date));
}

/** The days the court's own hearing history links business for ("Business on
 * Date"). Only these can ever be fetched, so a passed hearing on any other
 * day will never get an entry from "Check now". */
export function listedBusinessDays(hearings: readonly Pick<Hearing, "business_date">[]): Set<string> {
  const days = new Set<string>();
  for (const h of hearings) if (h.business_date) days.add(plainDayKey(h.business_date));
  return days;
}

export type HearingBusinessInfo =
  /** Not a district case: nothing to show. */
  | { kind: "off" }
  /** Nothing to say yet: a hearing still ahead, or a cancelled one. */
  | { kind: "none" }
  | { kind: "loading" }
  | { kind: "error" }
  | { kind: "entry"; entry: DailyStatusEntry }
  /** A passed hearing whose business the court lists but we have not saved. */
  | { kind: "missing" }
  /** A passed hearing the court's history lists no business for. */
  | { kind: "unlisted" };

export interface HearingBusinessInputs {
  enabled: boolean;
  status: "loading" | "error" | "ready";
  index: ReadonlyMap<string, DailyStatusEntry>;
  listed: ReadonlySet<string>;
  /** The India date today, YYYY-MM-DD. */
  today: string;
}

/** What to show for one hearing. A saved entry always shows, whatever the
 * hearing's status (a hearing today can already have its business). Without
 * one, only a day that has passed says anything. */
export function hearingBusinessInfo(
  hearing: Pick<Hearing, "hearing_date" | "status" | "business_date">,
  { enabled, status, index, listed, today }: HearingBusinessInputs,
): HearingBusinessInfo {
  if (!enabled) return { kind: "off" };
  const day = hearingDayKey(hearing.hearing_date);
  // Today or earlier: its business may exist (or be on the way).
  if (day > today) return { kind: "none" };
  if (status === "loading") return { kind: "loading" };
  if (status === "error") return { kind: "error" };
  const entry = index.get(day);
  if (entry) return { kind: "entry", entry };
  if (day === today || hearing.status === "cancelled") return { kind: "none" };
  return listed.has(day) ? { kind: "missing" } : { kind: "unlisted" };
}

/** The business text as one line for a row preview: line breaks and runs of
 * spaces collapsed. */
export function oneLine(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

/** The line shown when "Check now" is refused or fails. A 429 is the
 * server's cooldown between order checks; it says how long to wait. */
export function checkErrorNote(error: unknown): string {
  if (error instanceof APIError && error.status === 429) {
    const seconds = Number((error.data as { retry_after?: unknown } | null)?.retry_after);
    const wait =
      Number.isFinite(seconds) && seconds > 0
        ? `Try again in about ${Math.max(1, Math.ceil(seconds / 60))} min.`
        : "Try again in a few minutes.";
    return `A check just ran. ${wait}`;
  }
  return apiErrorDetail(error, "Could not start the check. Try again in a moment.");
}
