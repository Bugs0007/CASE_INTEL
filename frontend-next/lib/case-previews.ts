import { isOpenTask, localIsoDate } from "@/lib/tasks";
import type {
  ClientContact,
  CourtOrder,
  Document,
  Hearing,
  NestedAppearanceFee,
  Task,
} from "@/types";

/** What each card on the case page shows before it is expanded.
 *
 * Every rule lives here, as a plain function of the data, so the cards stay
 * layout-only and the rules can be tested without rendering anything. The
 * expanded dialog shows the whole list, so the cards pass the same arrays to
 * both and only the selection differs. */

export const TASK_PREVIEW_MAX = 3;
export const HEARING_PAST_PREVIEW = 2;
export const DOCUMENT_PREVIEW_MAX = 4;
export const FEE_PREVIEW_MAX = 3;
export const CONTACT_PREVIEW_MAX = 2;
export const DAY_CELL_MAX = 2;
/** The expanded dialog gets a search box once it lists more than this. */
export const SEARCH_THRESHOLD = 8;

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export function showSearch(itemCount: number): boolean {
  return itemCount > SEARCH_THRESHOLD;
}

/** Every word of `query` appears somewhere in `fields` (case-insensitive).
 * A blank query matches everything. */
export function matchesQuery(
  query: string,
  ...fields: (string | null | undefined)[]
): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = fields.filter(Boolean).join(" ").toLowerCase();
  return words.every((word) => haystack.includes(word));
}

// ---------------------------------------------------------------------------
// Tasks & Deadlines
// ---------------------------------------------------------------------------

function dayOf(date: string): string {
  return date.slice(0, 10);
}

/** Open tasks in the order an advocate should look at them: overdue first
 * (the longest overdue at the top), then the soonest due, then anything with
 * no date. */
export function sortOpenTasks(tasks: readonly Task[], today: string = localIsoDate()): Task[] {
  const rank = (task: Task) => {
    if (!task.due_date) return 2;
    return dayOf(task.due_date) < today ? 0 : 1;
  };
  return tasks
    .filter(isOpenTask)
    .slice()
    .sort((a, b) => {
      const byRank = rank(a) - rank(b);
      if (byRank !== 0) return byRank;
      if (a.due_date && b.due_date) {
        const byDate = dayOf(a.due_date).localeCompare(dayOf(b.due_date));
        if (byDate !== 0) return byDate;
      }
      return a.id - b.id;
    });
}

/** The card: at most `max` open tasks. Completed and dismissed ones never
 * appear here. */
export function previewTasks(
  tasks: readonly Task[],
  max: number = TASK_PREVIEW_MAX,
  today: string = localIsoDate(),
): Task[] {
  return sortOpenTasks(tasks, today).slice(0, max);
}

/** The dialog: every open task in the same order, then the closed ones, the
 * most recently finished first. */
export function expandedTasks(
  tasks: readonly Task[],
  today: string = localIsoDate(),
): { open: Task[]; closed: Task[] } {
  const closed = tasks
    .filter((task) => !isOpenTask(task))
    .slice()
    .sort(
      (a, b) =>
        (b.completed_at ?? b.updated_at).localeCompare(a.completed_at ?? a.updated_at) ||
        b.id - a.id,
    );
  return { open: sortOpenTasks(tasks, today), closed };
}

// ---------------------------------------------------------------------------
// Hearings & Orders
// ---------------------------------------------------------------------------

/** Upcoming = still scheduled and not yet past, soonest first. Past =
 * everything else (heard, cancelled, or a date that has gone by), most
 * recent first. */
export function splitHearings(
  hearings: readonly Hearing[],
  now: Date = new Date(),
): { upcoming: Hearing[]; past: Hearing[] } {
  const time = (h: Hearing) => new Date(h.hearing_date).getTime();
  const upcoming: Hearing[] = [];
  const past: Hearing[] = [];
  for (const hearing of hearings) {
    if (hearing.status === "scheduled" && time(hearing) >= now.getTime()) upcoming.push(hearing);
    else past.push(hearing);
  }
  upcoming.sort((a, b) => time(a) - time(b) || a.id - b.id);
  past.sort((a, b) => time(b) - time(a) || b.id - a.id);
  return { upcoming, past };
}

export function nextHearing(hearings: readonly Hearing[], now: Date = new Date()): Hearing | null {
  return splitHearings(hearings, now).upcoming[0] ?? null;
}

/** The card: the next upcoming hearing, then the most recent past ones. */
export function previewHearings(
  hearings: readonly Hearing[],
  now: Date = new Date(),
  pastCount: number = HEARING_PAST_PREVIEW,
): { next: Hearing | null; recent: Hearing[] } {
  const { upcoming, past } = splitHearings(hearings, now);
  return { next: upcoming[0] ?? null, recent: past.slice(0, pastCount) };
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

function documentDay(doc: Document): string {
  return doc.document_date ? dayOf(doc.document_date) : dayOf(doc.created_at);
}

/** The newest court order on file. Orders are dated by the order itself
 * where the document knows it, else by when it was added. */
export function latestOrderDocument(documents: readonly Document[]): Document | null {
  let latest: Document | null = null;
  for (const doc of documents) {
    if (doc.document_type !== "court_order") continue;
    if (
      !latest ||
      documentDay(doc).localeCompare(documentDay(latest)) > 0 ||
      (documentDay(doc) === documentDay(latest) &&
        (doc.created_at.localeCompare(latest.created_at) > 0 ||
          (doc.created_at === latest.created_at && doc.id > latest.id)))
    ) {
      latest = doc;
    }
  }
  return latest;
}

/** Every document: the latest order pinned first, then the rest newest
 * upload first. */
export function sortDocuments(documents: readonly Document[]): Document[] {
  const pinned = latestOrderDocument(documents);
  const rest = documents
    .filter((doc) => doc !== pinned)
    .slice()
    .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id);
  return pinned ? [pinned, ...rest] : rest;
}

export function previewDocuments(
  documents: readonly Document[],
  max: number = DOCUMENT_PREVIEW_MAX,
): Document[] {
  return sortDocuments(documents).slice(0, max);
}

// ---------------------------------------------------------------------------
// Fees & billing
// ---------------------------------------------------------------------------

/** A charge together with the hearing it belongs to. Fees are nested under
 * hearings in the API, so the case-wide list is built from the hearings the
 * page already loaded. */
export interface CaseFee {
  fee: NestedAppearanceFee;
  hearing: Hearing;
}

export function flattenFees(hearings: readonly Hearing[]): CaseFee[] {
  return hearings.flatMap((hearing) =>
    (hearing.appearance_fees ?? []).map((fee) => ({ fee, hearing })),
  );
}

/** Unpaid (pending or invoiced) first, the longest outstanding at the top;
 * then paid, the most recently paid first. */
export function sortFees(fees: readonly CaseFee[]): CaseFee[] {
  const unpaid = (item: CaseFee) => item.fee.status !== "paid";
  const hearingTime = (item: CaseFee) => new Date(item.hearing.hearing_date).getTime();
  const paidAt = (item: CaseFee) => item.fee.paid_at ?? item.hearing.hearing_date;
  return fees.slice().sort((a, b) => {
    if (unpaid(a) !== unpaid(b)) return unpaid(a) ? -1 : 1;
    if (unpaid(a)) return hearingTime(a) - hearingTime(b) || a.fee.id - b.fee.id;
    return paidAt(b).localeCompare(paidAt(a)) || b.fee.id - a.fee.id;
  });
}

export function previewFees(fees: readonly CaseFee[], max: number = FEE_PREVIEW_MAX): CaseFee[] {
  return sortFees(fees).slice(0, max);
}

// ---------------------------------------------------------------------------
// Client contacts
// ---------------------------------------------------------------------------

/** The primary contact, then the billing contact, then the rest in the
 * order the API gave them. One person who is both counts once, first. */
export function sortContacts(contacts: readonly ClientContact[]): ClientContact[] {
  const rank = (c: ClientContact) => (c.role === "primary" ? 0 : c.is_billing_contact ? 1 : 2);
  return contacts
    .map((contact, index) => ({ contact, index }))
    .sort((a, b) => rank(a.contact) - rank(b.contact) || a.index - b.index)
    .map(({ contact }) => contact);
}

export function previewContacts(
  contacts: readonly ClientContact[],
  max: number = CONTACT_PREVIEW_MAX,
): ClientContact[] {
  return sortContacts(contacts).slice(0, max);
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

/** What a month-grid day cell lists: the first `limit` items, and how many
 * more there are (shown as "+n more"). A day with exactly `limit` items has
 * none hidden. */
export function dayCellSummary<T>(
  items: readonly T[] | undefined,
  limit: number = DAY_CELL_MAX,
): { visible: T[]; hidden: number } {
  const all = items ?? [];
  return { visible: all.slice(0, limit), hidden: Math.max(0, all.length - limit) };
}

// ---------------------------------------------------------------------------
// Order Overview
// ---------------------------------------------------------------------------

/** The order whose overview sits on the card: the most recent DATED one.
 * Undated orders can't be sequenced, so they never win the slot. */
export function latestOrderForOverview(orders: readonly CourtOrder[]): CourtOrder | null {
  let latest: CourtOrder | null = null;
  for (const order of orders) {
    if (!order.order_date) continue;
    if (!latest || order.order_date > (latest.order_date ?? "")) latest = order;
  }
  return latest;
}

/** The dialog: every order that has an overview (a summary still being
 * generated has nothing to show), newest first, undated ones last. */
export function ordersWithOverview(orders: readonly CourtOrder[]): CourtOrder[] {
  return orders
    .filter((order) => order.summary && order.summary.status !== "pending")
    .slice()
    .sort((a, b) => {
      if (!!a.order_date !== !!b.order_date) return a.order_date ? -1 : 1;
      return (b.order_date ?? "").localeCompare(a.order_date ?? "") || b.id - a.id;
    });
}
