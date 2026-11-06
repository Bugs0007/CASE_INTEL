import { hearingDayKey } from "@/lib/calendar";
import { isOpenTask } from "@/lib/tasks";
import { hasPlaceholderTitle } from "@/lib/utils";
import type {
  ChangedDate,
  DashCase,
  DashDraft,
  DashFailedDoc,
  DashHearing,
  DashTask,
  DashUnbilled,
  LastOrder,
} from "@/lib/dashboard/model";
import type {
  Case,
  ClientMessage,
  Document,
  Hearing,
  Task,
  UninvoicedHearing,
  UpcomingHearing,
} from "@/types";

/** The API types, reduced to the shapes lib/dashboard/model.ts works on.
 * Nothing here fetches anything: it only reads what the dashboard already
 * loaded. */

/** What to call a case on screen: its title, or the case number when the
 * title is only a placeholder. */
export function caseDisplayTitle(title: string, caseNumber: string): string {
  return hasPlaceholderTitle({ title, cnr_number: null, case_number: caseNumber })
    ? caseNumber || title
    : title || caseNumber;
}

export function toDashCase(c: Case): DashCase {
  return {
    id: c.id,
    title: caseDisplayTitle(c.title, c.case_number),
    number: c.case_number,
    status: c.status,
    courtFallback: "",
  };
}

export function toDashHearing(h: Hearing, titles?: ReadonlyMap<number, string>): DashHearing {
  return {
    id: h.id,
    caseId: h.case,
    caseTitle: titles?.get(h.case) ?? h.case_title,
    day: hearingDayKey(h.hearing_date),
    court: (h.location ?? "").trim(),
    hall: (h.cause_list_court_hall ?? "").trim(),
    item: (h.cause_list_item_number ?? "").trim(),
    state: h.cause_list_status,
    scheduled: h.status === "scheduled",
  };
}

/** Open tasks only; a completed or dismissed task is not owed. */
export function toDashTasks(tasks: readonly Task[]): DashTask[] {
  return tasks.filter(isOpenTask).map((t) => ({
    id: t.id,
    caseId: t.case,
    caseTitle: t.case_title ? caseDisplayTitle(t.case_title, t.case_number ?? "") : "",
    title: t.title,
    due: t.due_date ? t.due_date.slice(0, 10) : null,
    kind: t.kind,
  }));
}

/** The newest order Overview we already hold for each case.
 *
 * Every hearing carries the Order Overview of the order filed on its own
 * date, so the last order of a case is the summary on its most recent
 * hearing (today or earlier) that has one -- no request per case. */
export function lastOrdersByCase(
  hearings: readonly Hearing[],
  today: string,
): Map<number, LastOrder> {
  const out = new Map<number, LastOrder>();
  const summaryDay = (h: Hearing) => hearingDayKey(h.hearing_date);
  const sorted = hearings
    .filter((h) => h.order_summary && summaryDay(h) <= today)
    .sort((a, b) => summaryDay(b).localeCompare(summaryDay(a)) || b.id - a.id);

  for (const h of sorted) {
    if (out.has(h.case)) continue;
    const summary = h.order_summary!;
    if (summary.status === "pending" || summary.status === "failed" || summary.status === "unreadable") continue;
    const text = summary.what_happened?.trim();
    if (!text) continue;
    out.set(h.case, { day: summaryDay(h), text });
  }
  return out;
}

/** Hearings eCourts touched since the advocate's last visit. */
export function toChanged(updates: readonly UpcomingHearing[]): ChangedDate[] {
  return updates
    .filter((u) => u.source === "ecourts")
    .map((u) => ({ hearingId: u.id, caseId: u.case_id, day: hearingDayKey(u.hearing_date) }));
}

export function toFailedDocs(documents: readonly Document[]): DashFailedDoc[] {
  return documents.map((d) => ({
    id: d.id,
    caseId: d.case_id,
    caseTitle: d.case ? caseDisplayTitle(d.case.title, d.case.case_number) : (d.case_title ?? ""),
    filename: d.filename,
  }));
}

export function toUnbilled(rows: readonly UninvoicedHearing[]): DashUnbilled[] {
  // A hearing with a fee recorded but no invoice is as uninvoiced as one with
  // no fee at all, so both stay.
  return rows.map((r) => ({
    hearingId: r.hearing_id,
    caseId: r.case_id,
    caseTitle: caseDisplayTitle(r.case_title, r.case_number),
    day: hearingDayKey(r.hearing_date),
  }));
}

export function toDrafts(messages: readonly ClientMessage[]): DashDraft[] {
  return messages.map((m) => ({
    id: m.id,
    caseId: m.case,
    caseTitle: caseDisplayTitle(m.case_title, m.case_number),
    kind: m.kind,
  }));
}
