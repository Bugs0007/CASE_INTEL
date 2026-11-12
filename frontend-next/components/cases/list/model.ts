import { hearingDayKey } from "@/lib/calendar";
import { daysBetween, shortDay } from "@/lib/dashboard/dates";
import { orderCheckMarker } from "@/components/cases/order-sync-status";
import { pluralize } from "@/lib/utils";
import type { Case } from "@/types";

/** How the Cases list is ordered. Plain TypeScript, no React. */
export type CaseSort = "hearing" | "title" | "updated";

export const SORT_OPTIONS: { key: CaseSort; label: string }[] = [
  { key: "hearing", label: "Next hearing" },
  { key: "title", label: "Title" },
  { key: "updated", label: "Recently updated" },
];

export function parseSort(value: string): CaseSort {
  return value === "title" || value === "updated" ? value : "hearing";
}

function byTitle(a: Case, b: Case): number {
  return a.title.localeCompare(b.title, "en", { sensitivity: "base" }) || a.id - b.id;
}

/** The newest sign of life: the last court fetch, else when the case was added.
 * (The list API carries no updated_at.) */
function touchedAt(c: Case): number {
  const t = Date.parse(c.last_fetched_at ?? c.created_at);
  return Number.isNaN(t) ? 0 : t;
}

/** `cases` in the chosen order; the input is not changed.
 *
 * "hearing": upcoming hearings soonest first, then cases whose last listed
 * hearing has passed (most recent first), then cases with no hearing. Ties and
 * the other sorts fall back to the title. */
export function sortCases(cases: Case[], sort: CaseSort, today: string): Case[] {
  const out = cases.slice();
  if (sort === "title") return out.sort(byTitle);
  if (sort === "updated") return out.sort((a, b) => touchedAt(b) - touchedAt(a) || byTitle(a, b));

  const day = (c: Case) => (c.next_hearing_date ? hearingDayKey(c.next_hearing_date) : null);
  const rank = (d: string | null) => (d === null ? 2 : d >= today ? 0 : 1);
  return out.sort((a, b) => {
    const da = day(a);
    const db = day(b);
    const ra = rank(da);
    const rb = rank(db);
    if (ra !== rb) return ra - rb;
    if (da !== null && db !== null && da !== db) {
      // Upcoming: soonest first. Past: latest first.
      return ra === 0 ? (da < db ? -1 : 1) : da < db ? 1 : -1;
    }
    return byTitle(a, b);
  });
}

export type AttentionKind = "hearing" | "docs" | "order" | "ecourts";

export interface AttentionReason {
  kind: AttentionKind;
  label: string;
  tone: "pending" | "alert" | "none";
}

export interface AttentionContext {
  today: string;
  /** Cases with a hearing in the next 7 days (the Dashboard's definition). */
  hearingSoonIds: ReadonlySet<number>;
  /** Case id -> how many of its documents failed processing. */
  failedDocCounts: ReadonlyMap<number, number>;
  ecourtsUpdateIds: ReadonlySet<number>;
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function hearingLabel(c: Case, today: string): string {
  if (!c.next_hearing_date) return "Hearing this week";
  const day = hearingDayKey(c.next_hearing_date);
  const diff = daysBetween(today, day);
  if (diff < 0 || diff > 7) return "Hearing this week";
  if (diff === 0) return "Hearing today";
  if (diff === 1) return "Hearing tomorrow";
  return `Hearing ${WEEKDAYS[new Date(`${day}T00:00:00`).getDay()]}`;
}

/** Why a case needs a look, most urgent first. Empty when nothing does. */
export function attentionReasons(c: Case, ctx: AttentionContext): AttentionReason[] {
  const out: AttentionReason[] = [];
  const failed = ctx.failedDocCounts.get(c.id) ?? 0;
  if (failed > 0) out.push({ kind: "docs", label: `${pluralize(failed, "doc")} failed`, tone: "alert" });
  const order = orderCheckMarker(c);
  if (order) out.push({ kind: "order", label: order.charAt(0).toUpperCase() + order.slice(1), tone: "pending" });
  if (ctx.hearingSoonIds.has(c.id)) out.push({ kind: "hearing", label: hearingLabel(c, ctx.today), tone: "pending" });
  if (ctx.ecourtsUpdateIds.has(c.id)) out.push({ kind: "ecourts", label: "eCourts update", tone: "none" });
  return out;
}

/** The attention filters the strip offers (eCourts updates are shown on the
 * row but are not a filter). */
export type AttentionFilter = "hearing" | "order" | "docs";

export const ATTENTION_FILTERS: { key: AttentionFilter; label: string }[] = [
  { key: "hearing", label: "Hearing this week" },
  { key: "order", label: "Order check failed" },
  { key: "docs", label: "Documents failed" },
];

/** What a case's next hearing reads as in the list. */
export interface HearingCell {
  /** "Thu 12 Nov", or "" with no hearing. */
  date: string;
  /** "Today", "Tomorrow", "In 3 days", "2 days ago", or "". */
  relative: string;
  upcoming: boolean;
  /** Today or tomorrow: worth emphasising. */
  soon: boolean;
}

export function hearingCell(c: Case, today: string): HearingCell {
  if (!c.next_hearing_date) return { date: "", relative: "", upcoming: false, soon: false };
  const day = hearingDayKey(c.next_hearing_date);
  const diff = daysBetween(today, day);
  const relative =
    diff === 0
      ? "Today"
      : diff === 1
        ? "Tomorrow"
        : diff > 1
          ? `In ${pluralize(diff, "day")}`
          : diff === -1
            ? "Yesterday"
            : `${-diff} days ago`;
  return { date: shortDay(day), relative, upcoming: diff >= 0, soon: diff === 0 || diff === 1 };
}
