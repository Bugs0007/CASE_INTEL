import { hearingDayKey } from "@/lib/calendar";
import { daysBetween } from "@/lib/dashboard/dates";
import type { AgingBucket, AppearanceFee, Case, ClientType } from "@/types";

/** What the Billing page works out from the fee list and the case list, as
 * plain functions so it can be tested. Days are India day keys
 * ("YYYY-MM-DD"); money is kept in whole paise while it is added up, so a
 * column of rupee amounts never picks up a stray 0.0000001. */

/** Which charges the list shows. "open" is everything unpaid. */
export type BillingFilter = "open" | "to_invoice" | "awaiting" | "paid";

export const BILLING_FILTERS: BillingFilter[] = ["open", "to_invoice", "awaiting", "paid"];

/** An invoice unpaid for longer than this is overdue: the same line the
 * aging buckets draw between "0-30" and "31-60". */
export const OVERDUE_AFTER_DAYS = 30;

/** Paid charges listed before "Show older" -- a long history is not the job
 * of this page. */
export const PAID_PAGE_SIZE = 20;

export function toPaise(amount: string | number): number {
  const n = typeof amount === "number" ? amount : Number(amount);
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

export function fromPaise(paise: number): number {
  return paise / 100;
}

/** One charge with what the page needs to show it: its client and case
 * (the fee itself only knows its case id and title). */
export interface FeeRow {
  fee: AppearanceFee;
  paise: number;
  /** "client:12" for a charge on a client's case, "case:42" for a case that
   * is not linked to a client. */
  groupKey: string;
  clientId: number | null;
  /** The linked client's name; "" for a case without one. */
  clientName: string;
  clientType: ClientType | null;
  caseNumber: string;
  caseTitle: string;
  /** Whole days since the invoice (India dates); null unless invoiced. */
  ageDays: number | null;
  overdue: boolean;
  /** India date of the hearing the charge belongs to. */
  hearingDay: string;
  paidDay: string | null;
}

/** Days an invoice has been out. Like the server's aging, counted from the
 * India date of `invoiced_at`; an invoice with no date counts as today's. */
export function invoiceAgeDays(invoicedAt: string | null, today: string): number {
  const day = invoicedAt ? hearingDayKey(invoicedAt) : today;
  return Math.max(daysBetween(day, today), 0);
}

/** Join the fees to their cases and drop the Rs. 0 charges (an appearance
 * fee recorded before a default fee was set): nothing is owed on them, and
 * the server's own totals leave them out too. */
export function buildFeeRows(fees: AppearanceFee[], cases: Case[], today: string): FeeRow[] {
  const byId = new Map(cases.map((c) => [c.id, c]));
  const rows: FeeRow[] = [];
  for (const fee of fees) {
    const paise = toPaise(fee.amount);
    if (paise <= 0) continue;
    const found = byId.get(fee.case_id);
    const client = found?.client_detail ?? null;
    const ageDays = fee.status === "invoiced" ? invoiceAgeDays(fee.invoiced_at, today) : null;
    rows.push({
      fee,
      paise,
      groupKey: client ? `client:${client.id}` : `case:${fee.case_id}`,
      clientId: client?.id ?? null,
      clientName: client?.name ?? "",
      clientType: client?.client_type ?? null,
      caseNumber: found?.case_number ?? "",
      caseTitle: found?.title ?? fee.case_title,
      ageDays,
      overdue: ageDays !== null && ageDays > OVERDUE_AFTER_DAYS,
      hearingDay: hearingDayKey(fee.hearing_date),
      paidDay: fee.paid_at ? hearingDayKey(fee.paid_at) : null,
    });
  }
  return rows;
}

export interface Tally {
  paise: number;
  count: number;
}

export interface BillingSummary {
  /** Recorded, no invoice yet. */
  toInvoice: Tally;
  /** Invoiced, not paid. */
  awaiting: Tally & { overdueCount: number; oldestDays: number | null };
  /** toInvoice + awaiting: everything unpaid. */
  outstanding: Tally;
  /** Paid in the current India month. */
  paidThisMonth: Tally;
}

export function summarize(rows: FeeRow[], today: string): BillingSummary {
  const toInvoice: Tally = { paise: 0, count: 0 };
  const awaiting = { paise: 0, count: 0, overdueCount: 0, oldestDays: null as number | null };
  const paidThisMonth: Tally = { paise: 0, count: 0 };
  const month = today.slice(0, 7);
  for (const row of rows) {
    if (row.fee.status === "pending") {
      toInvoice.paise += row.paise;
      toInvoice.count += 1;
    } else if (row.fee.status === "invoiced") {
      awaiting.paise += row.paise;
      awaiting.count += 1;
      if (row.overdue) awaiting.overdueCount += 1;
      if (row.ageDays !== null && (awaiting.oldestDays === null || row.ageDays > awaiting.oldestDays)) {
        awaiting.oldestDays = row.ageDays;
      }
    } else if (row.paidDay && row.paidDay.slice(0, 7) === month) {
      paidThisMonth.paise += row.paise;
      paidThisMonth.count += 1;
    }
  }
  return {
    toInvoice,
    awaiting,
    outstanding: { paise: toInvoice.paise + awaiting.paise, count: toInvoice.count + awaiting.count },
    paidThisMonth,
  };
}

const BUCKETS: { label: AgingBucket["label"]; from: number; to: number | null }[] = [
  { label: "0-30", from: 0, to: 30 },
  { label: "31-60", from: 31, to: 60 },
  { label: "61-90", from: 61, to: 90 },
  { label: "90+", from: 91, to: null },
];

/** Invoiced-and-unpaid money by how long it has been out (the same buckets
 * as the server's portfolio, worked out here so the card moves the moment a
 * charge is marked paid). */
export function agingBuckets(rows: FeeRow[]): AgingBucket[] {
  return BUCKETS.map(({ label, from, to }) => {
    let paise = 0;
    let count = 0;
    for (const row of rows) {
      if (row.ageDays === null) continue;
      if (row.ageDays >= from && (to === null || row.ageDays <= to)) {
        paise += row.paise;
        count += 1;
      }
    }
    return { label, count, amount: fromPaise(paise).toFixed(2) };
  });
}

/** Does the charge belong to this filter? */
export function inFilter(row: FeeRow, filter: BillingFilter): boolean {
  const status = row.fee.status;
  if (filter === "open") return status === "pending" || status === "invoiced";
  if (filter === "to_invoice") return status === "pending";
  if (filter === "awaiting") return status === "invoiced";
  return status === "paid";
}

/** Every word typed must be found somewhere in the client, case, invoice
 * number or kind of charge. */
export function matchesQuery(row: FeeRow, query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = [
    row.clientName,
    row.caseNumber,
    row.caseTitle,
    row.fee.invoice_number,
    row.fee.category_display,
  ]
    .join(" ")
    .toLowerCase();
  return words.every((word) => haystack.includes(word));
}

export function filterRows(rows: FeeRow[], filter: BillingFilter, query: string): FeeRow[] {
  return rows.filter((row) => inFilter(row, filter) && matchesQuery(row, query));
}

/** The `limit` most recently paid of `rows`. */
export function newestPaid(rows: FeeRow[], limit: number): FeeRow[] {
  return [...rows]
    .sort((a, b) => (b.fee.paid_at ?? "").localeCompare(a.fee.paid_at ?? "") || b.fee.id - a.fee.id)
    .slice(0, limit);
}

export interface FeeGroup {
  key: string;
  /** The client; null for a case that is not linked to one. */
  clientId: number | null;
  clientType: ClientType | null;
  /** The client's name, or the case number for an unlinked case. */
  title: string;
  /** Cases the shown charges are on, or the case's title when unlinked. */
  subtitle: string;
  /** For an unlinked case: where the "assign a client" control points. */
  caseId: number | null;
  rows: FeeRow[];
  /** The invoiced rows among `rows` (what "Mark all paid" would settle). */
  invoiced: FeeRow[];
  /** Unpaid money (to invoice + awaiting) among `rows`. */
  unpaidPaise: number;
  /** Paid money among `rows`. */
  paidPaise: number;
  oldestDays: number | null;
}

const STATUS_ORDER = { invoiced: 0, pending: 1, paid: 2 } as const;

function compareRows(a: FeeRow, b: FeeRow): number {
  const byStatus = STATUS_ORDER[a.fee.status] - STATUS_ORDER[b.fee.status];
  if (byStatus !== 0) return byStatus;
  if (a.fee.status === "invoiced") return (b.ageDays ?? 0) - (a.ageDays ?? 0) || a.fee.id - b.fee.id;
  if (a.fee.status === "paid") return (b.fee.paid_at ?? "").localeCompare(a.fee.paid_at ?? "") || b.fee.id - a.fee.id;
  return a.hearingDay.localeCompare(b.hearingDay) || a.fee.id - b.fee.id;
}

/** The rows grouped by client (or by case, when it has no client), the
 * group that needs a decision first on top: the longest-unpaid invoice,
 * then the most money, then the name. In the paid view, the group paid most
 * recently comes first. */
export function groupRows(rows: FeeRow[], filter: BillingFilter): FeeGroup[] {
  const groups = new Map<string, FeeGroup>();
  const cases = new Map<string, Set<number>>();
  for (const row of [...rows].sort(compareRows)) {
    let group = groups.get(row.groupKey);
    if (!group) {
      const unlinked = row.clientId === null;
      group = {
        key: row.groupKey,
        clientId: row.clientId,
        clientType: row.clientType,
        title: unlinked ? row.caseNumber || row.caseTitle : row.clientName,
        subtitle: unlinked ? (row.caseNumber ? row.caseTitle : "") : "",
        caseId: unlinked ? row.fee.case_id : null,
        rows: [],
        invoiced: [],
        unpaidPaise: 0,
        paidPaise: 0,
        oldestDays: null,
      };
      groups.set(row.groupKey, group);
      cases.set(row.groupKey, new Set());
    }
    group.rows.push(row);
    cases.get(row.groupKey)!.add(row.fee.case_id);
    if (row.fee.status === "invoiced") group.invoiced.push(row);
    if (row.fee.status === "paid") group.paidPaise += row.paise;
    else group.unpaidPaise += row.paise;
    if (row.ageDays !== null && (group.oldestDays === null || row.ageDays > group.oldestDays)) {
      group.oldestDays = row.ageDays;
    }
  }
  for (const group of groups.values()) {
    if (group.clientId !== null) {
      const n = cases.get(group.key)!.size;
      group.subtitle = `${n} case${n === 1 ? "" : "s"}`;
    }
  }
  const list = [...groups.values()];
  if (filter === "paid") {
    const latest = (g: FeeGroup) => g.rows[0]?.fee.paid_at ?? "";
    return list.sort((a, b) => latest(b).localeCompare(latest(a)) || a.title.localeCompare(b.title));
  }
  return list.sort(
    (a, b) =>
      (b.oldestDays ?? -1) - (a.oldestDays ?? -1) ||
      b.unpaidPaise - a.unpaidPaise ||
      a.title.localeCompare(b.title),
  );
}

/** "WP/1709/2026 · Butham Srinivas vs. State" -- an imported title often
 * starts with the number already, so it is not repeated. */
export function caseLabel(row: Pick<FeeRow, "caseNumber" | "caseTitle">): string {
  if (!row.caseNumber) return row.caseTitle;
  if (!row.caseTitle || row.caseTitle.includes(row.caseNumber)) return row.caseTitle || row.caseNumber;
  return `${row.caseNumber} · ${row.caseTitle}`;
}

/** "Invoiced today" / "Invoiced yesterday" / "Invoiced 12 days ago". */
export function invoicedWords(ageDays: number): string {
  if (ageDays === 0) return "Invoiced today";
  if (ageDays === 1) return "Invoiced yesterday";
  return `Invoiced ${ageDays} days ago`;
}

export interface FeeChip {
  tone: "none" | "pending" | "alert" | "ok";
  text: string;
}

/** The status chip on a charge's row: what state it is in and, for an
 * invoice past the overdue line, how long it has been unpaid. */
export function feeChip(row: FeeRow): FeeChip {
  if (row.fee.status === "pending") return { tone: "none", text: "To invoice" };
  if (row.fee.status === "paid") return { tone: "ok", text: "Paid" };
  if (row.overdue) return { tone: "alert", text: `${row.ageDays} days unpaid` };
  return { tone: "pending", text: "Awaiting payment" };
}
