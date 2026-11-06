import {
  addDays,
  dateLabel,
  dayMonth,
  daysBetween,
  longDate,
  shortDay,
} from "@/lib/dashboard/dates";
import {
  capitalizeFirst,
  clip,
  countOf,
  lowerFirst,
  numberWord,
  withoutFinalStop,
} from "@/lib/dashboard/text";

/** Everything the dashboard says, worked out from data that is already
 * loaded. Plain TypeScript, no React, so every sentence and every count can
 * be unit tested -- and the Briefing, the Glance column, the Practice map
 * and the legend all read the SAME result, so their numbers cannot
 * disagree.
 *
 * Inputs are small "Dash*" shapes (see lib/dashboard/adapt.ts for the
 * mapping from the API types). Dates are day keys ("YYYY-MM-DD") in India. */

// ---------------------------------------------------------------------------
// Inputs
// ---------------------------------------------------------------------------

/** Mirrors Hearing.cause_list_status. */
export type CauseState =
  | "not_checked"
  | "not_published"
  | "listed"
  | "not_listed"
  | "fetch_failed"
  | "unsupported";

export interface DashHearing {
  id: number;
  caseId: number;
  caseTitle: string;
  /** India date of the hearing. */
  day: string;
  /** The court as eCourts names it; "" when unknown. */
  court: string;
  hall: string;
  item: string;
  state: CauseState;
  /** Only a still-scheduled hearing counts as one. */
  scheduled: boolean;
}

export interface DashCase {
  id: number;
  title: string;
  number: string;
  /** Case.status: open / pending / closed / archived. */
  status: string;
  /** Used for the court band when no hearing names the court. */
  courtFallback: string;
}

/** An OPEN task (completed and dismissed ones are filtered out earlier). */
export interface DashTask {
  id: number;
  caseId: number | null;
  caseTitle: string;
  title: string;
  /** YYYY-MM-DD, or null when undated. */
  due: string | null;
  kind: string;
}

export interface LastOrder {
  /** The order's date (YYYY-MM-DD). */
  day: string;
  /** The Order Overview's "what happened". */
  text: string;
}

/** A hearing eCourts touched since the advocate's last visit. */
export interface ChangedDate {
  hearingId: number;
  caseId: number;
  day: string;
}

export interface DashFailedDoc {
  id: number;
  caseId: number | null;
  caseTitle: string;
  filename: string;
}

export interface DashUnbilled {
  hearingId: number;
  caseId: number;
  caseTitle: string;
  day: string;
}

export interface DashDraft {
  id: number;
  caseId: number;
  caseTitle: string;
  /** ClientMessage.kind: case_update or payment_reminder. */
  kind: string;
}

// ---------------------------------------------------------------------------
// Sentence pieces
// ---------------------------------------------------------------------------

/** A sentence is a list of pieces so the page can link the case title and
 * bold or italicise the rest without building HTML strings. */
export type Seg =
  | { kind: "text"; text: string }
  | { kind: "case"; text: string; caseId: number }
  | { kind: "em"; text: string }
  | { kind: "strong"; text: string };

const text = (value: string): Seg => ({ kind: "text", text: value });
const strong = (value: string): Seg => ({ kind: "strong", text: value });
const em = (value: string): Seg => ({ kind: "em", text: value });
const caseLink = (value: string, caseId: number): Seg => ({ kind: "case", text: value, caseId });

/** "today", "tomorrow", otherwise "Fri 6 Nov" -- for the middle of a sentence. */
function inlineDay(day: string, today: string): string {
  const label = dateLabel(day, today);
  return label === "Today" || label === "Tomorrow" ? label.toLowerCase() : label;
}

// ---------------------------------------------------------------------------
// Today
// ---------------------------------------------------------------------------

function numeric(value: string): number {
  const n = parseInt(value, 10);
  return Number.isNaN(n) ? Number.MAX_SAFE_INTEGER : n;
}

/** Hearings scheduled for `today`: listed ones first, then by court, hall
 * and item number. */
export function todaysHearings(hearings: readonly DashHearing[], today: string): DashHearing[] {
  return hearings
    .filter((h) => h.scheduled && h.day === today)
    .slice()
    .sort(
      (a, b) =>
        (a.state === "listed" ? 0 : 1) - (b.state === "listed" ? 0 : 1) ||
        a.court.localeCompare(b.court) ||
        numeric(a.hall) - numeric(b.hall) ||
        numeric(a.item) - numeric(b.item) ||
        a.id - b.id,
    );
}

/** The first scheduled hearing day after `today`, within `horizon` days. */
export function nextCourtDay(
  hearings: readonly DashHearing[],
  today: string,
  horizon = 14,
): string | null {
  let best: string | null = null;
  for (const h of hearings) {
    if (!h.scheduled || h.day <= today) continue;
    if (daysBetween(today, h.day) > horizon) continue;
    if (best === null || h.day < best) best = h.day;
  }
  return best;
}

/** "Two hearings today, and one is not on the cause list." Only a genuine
 * `not_listed` is counted as not on the list. */
export function leadSentence(
  todays: readonly DashHearing[],
  hearings: readonly DashHearing[],
  today: string,
): string {
  const n = todays.length;
  if (n === 0) {
    const next = nextCourtDay(hearings, today);
    return next
      ? `No hearings today. Your next court day is ${inlineDay(next, today)}.`
      : "No hearings in the next two weeks.";
  }
  const missing = todays.filter((h) => h.state === "not_listed").length;
  const head = n === 1 ? "One hearing" : `${capitalizeFirst(numberWord(n))} hearings`;
  const tail = missing
    ? `, and ${missing === 1 ? "one is" : `${missing} are`} not on the cause list`
    : "";
  return `${head} today${tail}.`;
}

/** How a cause-list state reads for a hearing, never claiming more than the
 * data says: "not on the list" is only said for `not_listed`. */
function causeListSegs(h: DashHearing): Seg[] {
  const court = h.court || "this court";
  switch (h.state) {
    case "not_listed":
      return [
        text(
          " is not on today's cause list. That can be a lag, so check the court's site before you leave.",
        ),
      ];
    case "not_published":
      return [text(` has a hearing today. The cause list for ${court} is not published yet.`)];
    case "fetch_failed":
      return [
        text(
          ` has a hearing today. We couldn't check the cause list for ${court}, so check the court's site.`,
        ),
      ];
    default:
      // not_checked, unsupported (a court we don't cover) or anything new.
      return [
        text(` has a hearing today. Cause lists are not tracked for ${court}, so check the court's site.`),
      ];
  }
}

function dueBy(due: string | null, today: string): string {
  if (!due) return "";
  const diff = daysBetween(today, due);
  if (diff < 0) return ` by ${shortDay(due)} (overdue)`;
  return ` by ${inlineDay(due, today)}`;
}

export interface HearingContext {
  today: string;
  lastOrder?: LastOrder | null;
  /** The case's most pressing open task. */
  task?: Pick<DashTask, "title" | "due"> | null;
}

/** One sentence (or two) for one of today's hearings. */
export function describeHearing(h: DashHearing, ctx: HearingContext): Seg[] {
  const segs: Seg[] = [caseLink(h.caseTitle, h.caseId)];

  if (h.state === "listed") {
    const where =
      (h.item ? ` at item ${h.item}` : "") +
      (h.hall ? `, hall ${h.hall}` : "") +
      (h.court ? `, ${h.court}` : "");
    segs.push(text(` is listed${where}.`));
  } else {
    segs.push(...causeListSegs(h));
  }

  if (ctx.lastOrder?.text) {
    segs.push(
      text(` The last order (${dayMonth(ctx.lastOrder.day)}) said `),
      em(lowerFirst(withoutFinalStop(clip(ctx.lastOrder.text, 220)))),
      text("."),
    );
  }

  if (h.state === "listed" && ctx.task) {
    segs.push(
      text(" You owe "),
      strong(lowerFirst(withoutFinalStop(ctx.task.title))),
      text(`${dueBy(ctx.task.due, ctx.today)}.`),
    );
  }
  return segs;
}

// ---------------------------------------------------------------------------
// Since yesterday
// ---------------------------------------------------------------------------

export interface SinceSummary {
  /** Cases whose hearing date eCourts changed. */
  count: number;
  /** Each such case with its earliest new date, soonest first. */
  items: { caseId: number; day: string }[];
  /** The earliest of the new dates. */
  earliest: string | null;
  /** A future day that now has hearings in 2+ courts, one of them a case
   * whose date just changed. */
  clash: { day: string; courts: number } | null;
}

export function distinctCourts(hearings: readonly DashHearing[]): string[] {
  return [...new Set(hearings.map((h) => h.court).filter(Boolean))];
}

export function sinceSummary(
  changed: readonly ChangedDate[],
  hearings: readonly DashHearing[],
  today: string,
): SinceSummary {
  const earliestByCase = new Map<number, string>();
  for (const c of changed) {
    const known = earliestByCase.get(c.caseId);
    if (known === undefined || c.day < known) earliestByCase.set(c.caseId, c.day);
  }
  const items = [...earliestByCase.entries()]
    .map(([caseId, day]) => ({ caseId, day }))
    .sort((a, b) => a.day.localeCompare(b.day) || a.caseId - b.caseId);

  // Only a day that holds a hearing eCourts just moved can be called a
  // clash "from the new dates"; an old clash is not news.
  const changedIds = new Set(changed.map((c) => c.hearingId));
  const byDay = new Map<string, DashHearing[]>();
  for (const h of hearings) {
    if (!h.scheduled || h.day <= today) continue;
    byDay.set(h.day, [...(byDay.get(h.day) ?? []), h]);
  }
  let clash: SinceSummary["clash"] = null;
  for (const day of [...byDay.keys()].sort()) {
    const onDay = byDay.get(day)!;
    const courts = distinctCourts(onDay);
    if (courts.length >= 2 && onDay.some((h) => changedIds.has(h.id))) {
      clash = { day, courts: courts.length };
      break;
    }
  }
  return { count: items.length, items, earliest: items[0]?.day ?? null, clash };
}

export type ChipTone = "ok" | "pending" | "alert" | "none";

/** The cause-list chip for a hearing -- the same words the hearing card and
 * the calendars use (components/hearings/cause-list-badge.tsx), so one state
 * never reads two ways. `null` when the list was never checked. */
export function causeChip(h: Pick<DashHearing, "state" | "item" | "hall">): { label: string; tone: ChipTone } | null {
  switch (h.state) {
    case "listed": {
      const parts = [h.item ? `Item ${h.item}` : null, h.hall ? `Court ${h.hall}` : null].filter(Boolean);
      return { label: parts.length ? parts.join(" · ") : "Listed", tone: "ok" };
    }
    case "not_published":
      return { label: "Not yet listed", tone: "none" };
    case "fetch_failed":
      return { label: "Couldn't check", tone: "alert" };
    case "unsupported":
      return { label: "Not covered", tone: "none" };
    case "not_listed":
      return { label: "Not listed", tone: "pending" };
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// The next 14 days
// ---------------------------------------------------------------------------

export interface DayBucket {
  day: string;
  label: string;
  count: number;
  courts: string[];
  /** Hearings in two or more different courts on this day. */
  multiCourt: boolean;
  hearings: DashHearing[];
}

export function buildDays(
  hearings: readonly DashHearing[],
  today: string,
  length = 14,
): DayBucket[] {
  return Array.from({ length }, (_, offset) => {
    const day = addDays(today, offset);
    const onDay = hearings.filter((h) => h.scheduled && h.day === day);
    const courts = distinctCourts(onDay);
    return {
      day,
      label: dateLabel(day, today),
      count: onDay.length,
      courts,
      multiCourt: courts.length >= 2,
      hearings: onDay,
    };
  });
}

export interface ComingUp {
  total: number;
  busiest: { day: string; count: number; courts: number } | null;
}

export function comingUp(days: readonly DayBucket[]): ComingUp {
  let busiest: ComingUp["busiest"] = null;
  for (const d of days) {
    if (d.count > 0 && (busiest === null || d.count > busiest.count)) {
      busiest = { day: d.day, count: d.count, courts: d.courts.length };
    }
  }
  return { total: days.reduce((sum, d) => sum + d.count, 0), busiest };
}

export function comingUpSegments(c: ComingUp, today: string): Seg[] {
  if (!c.busiest) return [text("No hearings in the next 14 days.")];
  const across = c.busiest.courts > 1 ? `, across ${c.busiest.courts} courts` : "";
  return [
    text(`${countOf(c.total, "hearing")} in the next 14 days. The busiest day is `),
    strong(dateLabel(c.busiest.day, today)),
    text(` with ${c.busiest.count}${across}.`),
  ];
}

// ---------------------------------------------------------------------------
// Needs you
// ---------------------------------------------------------------------------

export type NeedKind = "task" | "failed_document" | "unbilled" | "draft";

export interface NeedItem {
  key: string;
  kind: NeedKind;
  caseId: number | null;
  caseTitle: string;
  /** What is to be done, as a phrase that reads after "Title: ". */
  text: string;
  /** YYYY-MM-DD; null for an item with no date (it sorts last). */
  due: string | null;
  taskId?: number;
}

const NEED_RANK: Record<NeedKind, number> = { task: 0, unbilled: 1, draft: 2, failed_document: 3 };

export function buildNeeds(sources: {
  tasks: readonly DashTask[];
  failedDocs: readonly DashFailedDoc[];
  unbilled: readonly DashUnbilled[];
  drafts: readonly DashDraft[];
}): NeedItem[] {
  const items: NeedItem[] = [
    ...sources.tasks.map<NeedItem>((t) => ({
      key: `task-${t.id}`,
      kind: "task",
      caseId: t.caseId,
      caseTitle: t.caseTitle,
      text: t.title,
      due: t.due,
      taskId: t.id,
    })),
    ...sources.unbilled.map<NeedItem>((u) => ({
      key: `unbilled-${u.hearingId}`,
      kind: "unbilled",
      caseId: u.caseId,
      caseTitle: u.caseTitle,
      text: `the appearance on ${dayMonth(u.day)} is not invoiced`,
      due: null,
    })),
    ...sources.drafts.map<NeedItem>((d) => ({
      key: `draft-${d.id}`,
      kind: "draft",
      caseId: d.caseId,
      caseTitle: d.caseTitle,
      text:
        d.kind === "payment_reminder"
          ? "a payment reminder draft is waiting for review"
          : "a client update draft is waiting for review",
      due: null,
    })),
    ...sources.failedDocs.map<NeedItem>((d) => ({
      key: `doc-${d.id}`,
      kind: "failed_document",
      caseId: d.caseId,
      caseTitle: d.caseTitle,
      text: `a document failed processing (${d.filename})`,
      due: null,
    })),
  ];

  // Dated items first -- overdue ones lead because their dates are earliest --
  // then the undated ones.
  return items.sort((a, b) => {
    if ((a.due === null) !== (b.due === null)) return a.due === null ? 1 : -1;
    if (a.due !== null && b.due !== null && a.due !== b.due) return a.due.localeCompare(b.due);
    return NEED_RANK[a.kind] - NEED_RANK[b.kind] || a.key.localeCompare(b.key);
  });
}

/** ", 3 days overdue" / ", due today" / ", due Fri 6 Nov" / "". */
export function dueSuffix(due: string | null, today: string): string {
  if (!due) return "";
  const diff = daysBetween(today, due);
  if (diff < 0) return `, ${countOf(-diff, "day")} overdue`;
  return `, due ${inlineDay(due, today)}`;
}

export function needSegments(item: NeedItem, today: string): Seg[] {
  const phrase = `${lowerFirst(withoutFinalStop(item.text))}${dueSuffix(item.due, today)}.`;
  if (item.caseId === null || !item.caseTitle) return [text(capitalizeFirst(phrase))];
  return [caseLink(item.caseTitle, item.caseId), text(`: ${phrase}`)];
}

// ---------------------------------------------------------------------------
// The practice map
// ---------------------------------------------------------------------------

export type PracticeStatus = "today" | "attn" | "week" | "ecourts" | "quiet";

export const STATUS_ORDER: readonly PracticeStatus[] = ["today", "attn", "week", "ecourts", "quiet"];

export const STATUS_LABEL: Record<PracticeStatus, string> = {
  today: "Hearing today",
  attn: "Needs action",
  week: "Hearing this week",
  ecourts: "New date from eCourts",
  quiet: "Quiet",
};

/** The shorter names the Glance legend uses. */
export const STATUS_SHORT: Record<PracticeStatus, string> = {
  today: "Today",
  attn: "Needs action",
  week: "This week",
  ecourts: "New date",
  quiet: "Quiet",
};

export type AttnKind = "order_task" | "unbilled" | "draft" | "failed_doc" | "no_date";

const ATTN_REASON: Record<AttnKind, string> = {
  order_task: "Order task",
  unbilled: "Not invoiced",
  draft: "Draft waiting",
  failed_doc: "Document failed",
  no_date: "No next date",
};

export interface PracticeCase {
  id: number;
  title: string;
  number: string;
  court: string;
  status: PracticeStatus;
  attn: AttnKind | null;
  /** The one-line reason shown on the tile. */
  reason: string;
  nextDay: string | null;
  nextHearing: DashHearing | null;
  /** The date eCourts just moved this case to, if it did. */
  newDate: string | null;
}

export const COURT_UNKNOWN = "Court not recorded";

/** Case.status values that leave the practice map. A closed case with no
 * next date is finished, not neglected. */
export function isActiveCase(status: string): boolean {
  return status !== "closed" && status !== "archived";
}

/** The first party of "A vs B" -- what a map tile can fit. */
export function firstParty(title: string): string {
  const split = title.split(/\s+v(?:s|ersus)?\.?\s+/i)[0].trim();
  return split || title;
}

export interface ClassifyInput {
  today: string;
  cases: readonly DashCase[];
  hearings: readonly DashHearing[];
  tasks: readonly DashTask[];
  changed: readonly ChangedDate[];
  failedDocs: readonly DashFailedDoc[];
  unbilled: readonly DashUnbilled[];
  drafts: readonly DashDraft[];
}

function todayReason(h: DashHearing): string {
  if (h.state === "listed") return h.item ? `Today · item ${h.item}` : "Today · listed";
  if (h.state === "not_listed") return "Today · not listed";
  return "Today";
}

/** One status per case, evaluated in this order: hearing today, needs
 * action, hearing within 7 days, new date from eCourts, quiet. */
export function classifyCases(input: ClassifyInput): PracticeCase[] {
  const { today } = input;
  const withTask = new Set(
    input.tasks.filter((t) => t.kind === "order_direction" && t.caseId !== null).map((t) => t.caseId),
  );
  const withUnbilled = new Set(input.unbilled.map((u) => u.caseId));
  const withDraft = new Set(input.drafts.map((d) => d.caseId));
  const withFailedDoc = new Set(
    input.failedDocs.map((d) => d.caseId).filter((id): id is number => id !== null),
  );
  const newDates = new Map<number, string>();
  for (const c of input.changed) {
    const known = newDates.get(c.caseId);
    if (known === undefined || c.day < known) newDates.set(c.caseId, c.day);
  }

  const byCase = new Map<number, DashHearing[]>();
  for (const h of input.hearings) byCase.set(h.caseId, [...(byCase.get(h.caseId) ?? []), h]);

  return input.cases
    .filter((c) => isActiveCase(c.status))
    .map<PracticeCase>((c) => {
      const own = byCase.get(c.id) ?? [];
      const upcoming = own
        .filter((h) => h.scheduled && h.day >= today)
        .sort((a, b) => a.day.localeCompare(b.day) || a.id - b.id);
      const nextHearing = upcoming[0] ?? null;
      const nextDay = nextHearing?.day ?? null;

      // The court the case is heard in: the newest hearing that names one.
      const court =
        own
          .filter((h) => h.court)
          .sort((a, b) => b.day.localeCompare(a.day) || b.id - a.id)[0]?.court ||
        c.courtFallback ||
        COURT_UNKNOWN;

      const attn: AttnKind | null = withTask.has(c.id)
        ? "order_task"
        : withUnbilled.has(c.id)
          ? "unbilled"
          : withDraft.has(c.id)
            ? "draft"
            : withFailedDoc.has(c.id)
              ? "failed_doc"
              : nextDay === null
                ? "no_date"
                : null;

      const newDate = newDates.get(c.id) ?? null;
      const daysAway = nextDay === null ? null : daysBetween(today, nextDay);

      let status: PracticeStatus;
      let reason: string;
      if (nextHearing && daysAway === 0) {
        status = "today";
        reason = todayReason(nextHearing);
      } else if (attn) {
        status = "attn";
        reason = ATTN_REASON[attn];
      } else if (nextDay !== null && daysAway !== null && daysAway <= 7) {
        status = "week";
        reason = `Hearing ${shortDay(nextDay)}`;
      } else if (newDate) {
        status = "ecourts";
        reason = `New date ${dayMonth(newDate)}`;
      } else {
        status = "quiet";
        reason = "Quiet";
      }

      return {
        id: c.id,
        title: c.title,
        number: c.number,
        court,
        status,
        attn,
        reason,
        nextDay,
        nextHearing,
        newDate,
      };
    });
}

export function practiceCounts(cases: readonly PracticeCase[]): Record<PracticeStatus, number> {
  const counts: Record<PracticeStatus, number> = { today: 0, attn: 0, week: 0, ecourts: 0, quiet: 0 };
  for (const c of cases) counts[c.status] += 1;
  return counts;
}

function byUrgency(a: PracticeCase, b: PracticeCase): number {
  return (
    STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
    (a.nextDay ?? "9999").localeCompare(b.nextDay ?? "9999") ||
    a.title.localeCompare(b.title) ||
    a.id - b.id
  );
}

export interface Band {
  court: string;
  cases: PracticeCase[];
  /** Today + needs action + this week. */
  needLook: number;
  /** Cases shown as tiles. */
  tiles: PracticeCase[];
  /** New-date and quiet cases, shown as small squares. */
  squares: PracticeCase[];
  newDates: number;
  quiet: number;
}

/** One band per court, the busiest court first. */
export function buildBands(cases: readonly PracticeCase[]): Band[] {
  const byCourt = new Map<string, PracticeCase[]>();
  for (const c of cases) byCourt.set(c.court, [...(byCourt.get(c.court) ?? []), c]);

  return [...byCourt.entries()]
    .map<Band>(([court, own]) => {
      const sorted = own.slice().sort(byUrgency);
      const tiles = sorted.filter((c) => c.status === "today" || c.status === "attn" || c.status === "week");
      const squares = sorted.filter((c) => c.status === "ecourts" || c.status === "quiet");
      return {
        court,
        cases: sorted,
        needLook: tiles.length,
        tiles,
        squares,
        newDates: squares.filter((c) => c.status === "ecourts").length,
        quiet: squares.filter((c) => c.status === "quiet").length,
      };
    })
    .sort((a, b) => b.cases.length - a.cases.length || a.court.localeCompare(b.court));
}

/** The case the peek opens on: the most urgent one. */
export function defaultSelection(cases: readonly PracticeCase[]): number | null {
  return cases.slice().sort(byUrgency)[0]?.id ?? null;
}

/** Does a case match a search box? Party, number or court. */
export function caseMatches(c: PracticeCase, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = `${c.title} ${c.number} ${c.court}`.toLowerCase();
  return words.every((w) => haystack.includes(w));
}

// ---------------------------------------------------------------------------
// Heads up
// ---------------------------------------------------------------------------

export type Insight =
  | { kind: "clash"; day: string; courts: string[] }
  | { kind: "no_date"; count: number };

/** Only what the data supports. ("Out of town with no travel booked" is
 * left out: nothing records where a hearing is relative to the advocate.) */
export function buildInsights(days: readonly DayBucket[], cases: readonly PracticeCase[]): Insight[] {
  const insights: Insight[] = [];
  const clash = days.find((d) => d.multiCourt);
  if (clash) insights.push({ kind: "clash", day: clash.day, courts: clash.courts });
  const noDate = cases.filter((c) => c.nextDay === null).length;
  if (noDate > 0) insights.push({ kind: "no_date", count: noDate });
  return insights;
}

export function insightSegments(insight: Insight): Seg[] {
  if (insight.kind === "clash") {
    const shown = insight.courts.slice(0, 3).join(", ");
    const more = insight.courts.length > 3 ? ` and ${insight.courts.length - 3} more` : "";
    return [
      strong(shortDay(insight.day)),
      text(` has hearings in ${insight.courts.length} courts: ${shown}${more}.`),
    ];
  }
  return [
    strong(String(insight.count)),
    text(
      ` ${insight.count === 1 ? "case has" : "cases have"} no next hearing date. Refresh to check eCourts.`,
    ),
  ];
}

// ---------------------------------------------------------------------------
// Everything at once
// ---------------------------------------------------------------------------

export interface DashboardInput extends ClassifyInput {
  lastOrders: ReadonlyMap<number, LastOrder>;
}

export interface TodayRow {
  hearing: DashHearing;
  /** Case number, for the "all of today's hearings" list. */
  number: string;
  segments: Seg[];
}

/** A case eCourts moved to a new date, for the "N cases" list. */
export interface ChangedCaseRow {
  caseId: number;
  title: string;
  number: string;
  day: string;
}

export interface DashboardModel {
  today: string;
  dateLine: string;
  activeCaseCount: number;
  lead: string;
  /** Every hearing today, in display order. */
  todays: TodayRow[];
  since: SinceSummary;
  changedCases: ChangedCaseRow[];
  needs: NeedItem[];
  days: DayBucket[];
  comingUp: ComingUp;
  practice: PracticeCase[];
  counts: Record<PracticeStatus, number>;
  bands: Band[];
  insights: Insight[];
  defaultSelectedId: number | null;
  /** Open tasks per case, for the peek. */
  openTaskCount: ReadonlyMap<number, number>;
  lastOrders: ReadonlyMap<number, LastOrder>;
}

/** The most pressing open task of a case: soonest due, undated last. */
export function pressingTask(tasks: readonly DashTask[], caseId: number): DashTask | null {
  return (
    tasks
      .filter((t) => t.caseId === caseId)
      .sort((a, b) => {
        if ((a.due === null) !== (b.due === null)) return a.due === null ? 1 : -1;
        return (a.due ?? "").localeCompare(b.due ?? "") || a.id - b.id;
      })[0] ?? null
  );
}

export function buildDashboardModel(input: DashboardInput): DashboardModel {
  const { today } = input;
  const todays = todaysHearings(input.hearings, today);
  const days = buildDays(input.hearings, today);
  const practice = classifyCases(input);
  const openTaskCount = new Map<number, number>();
  for (const t of input.tasks) {
    if (t.caseId !== null) openTaskCount.set(t.caseId, (openTaskCount.get(t.caseId) ?? 0) + 1);
  }
  const caseById = new Map(input.cases.map((c) => [c.id, c]));
  const since = sinceSummary(input.changed, input.hearings, today);

  return {
    today,
    dateLine: longDate(today),
    activeCaseCount: practice.length,
    lead: leadSentence(todays, input.hearings, today),
    todays: todays.map((hearing) => ({
      hearing,
      number: caseById.get(hearing.caseId)?.number ?? "",
      segments: describeHearing(hearing, {
        today,
        lastOrder: input.lastOrders.get(hearing.caseId) ?? null,
        task: pressingTask(input.tasks, hearing.caseId),
      }),
    })),
    since,
    changedCases: since.items.map(({ caseId, day }) => ({
      caseId,
      day,
      title: caseById.get(caseId)?.title ?? `Case ${caseId}`,
      number: caseById.get(caseId)?.number ?? "",
    })),
    needs: buildNeeds(input),
    days,
    comingUp: comingUp(days),
    practice,
    counts: practiceCounts(practice),
    bands: buildBands(practice),
    insights: buildInsights(days, practice),
    defaultSelectedId: defaultSelection(practice),
    openTaskCount,
    lastOrders: input.lastOrders,
  };
}
