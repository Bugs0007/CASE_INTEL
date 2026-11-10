import { describe, expect, it } from "vitest";
import {
  agingBuckets,
  buildFeeRows,
  caseLabel,
  feeChip,
  filterRows,
  fromPaise,
  groupRows,
  invoiceAgeDays,
  invoicedWords,
  newestPaid,
  summarize,
  toPaise,
  type FeeRow,
} from "@/lib/billing-model";
import type { AppearanceFee, Case } from "@/types";

const TODAY = "2026-11-07";

/** An instant `days` India-days before TODAY, at noon IST (06:30 UTC). */
const ago = (days: number) => {
  const d = new Date(Date.UTC(2026, 10, 7 - days, 6, 30));
  return d.toISOString();
};

function fee(over: Partial<AppearanceFee> & { id: number }): AppearanceFee {
  return {
    category: "appearance",
    category_display: "Appearance Fee",
    amount: "5000.00",
    status: "pending",
    status_display: "Pending",
    invoice_number: "",
    invoiced_at: null,
    paid_at: null,
    sent_at: null,
    send_status: "not_sent",
    hearing: 1,
    case_id: 11,
    case_title: "Meera Nair vs. Sundaram Finance Ltd",
    hearing_date: "2026-10-12T00:00:00Z",
    invoice_sequence: null,
    sent_to_email: "",
    notes: "",
    created_at: "2026-10-12T00:00:00Z",
    updated_at: "2026-10-12T00:00:00Z",
    ...over,
  };
}

function kase(id: number, number: string, clientId: number | null, clientName = ""): Case {
  return {
    id,
    case_number: number,
    title: `Title of ${number}`,
    client: clientId,
    client_detail: clientId ? { id: clientId, name: clientName, client_type: "individual" } : null,
  } as unknown as Case;
}

const CASES = [
  kase(11, "CC/312/2026", 101, "Meera Nair"),
  kase(12, "WP/8841/2025", 102, "Rao & Sons Builders"),
  kase(13, "WP/1/2026", null),
];

const FEES = [
  fee({ id: 1, case_id: 11, status: "invoiced", invoice_number: "INV-0007", invoiced_at: ago(12), amount: "15000.00" }),
  fee({ id: 2, case_id: 11, status: "pending", amount: "3000.00" }),
  fee({ id: 3, case_id: 12, status: "invoiced", invoice_number: "INV-0003", invoiced_at: ago(41), amount: "8000.00" }),
  fee({ id: 4, case_id: 12, status: "invoiced", invoice_number: "INV-0005", invoiced_at: ago(5), amount: "4000.50" }),
  fee({ id: 5, case_id: 11, status: "paid", invoice_number: "INV-0001", invoiced_at: ago(40), paid_at: ago(3), amount: "6000.00" }),
  fee({ id: 6, case_id: 13, status: "pending", amount: "2500.00" }),
  fee({ id: 7, case_id: 13, status: "pending", amount: "0.00" }),
];

const rows = () => buildFeeRows(FEES, CASES, TODAY);

describe("money in paise", () => {
  it("adds up without floating-point noise", () => {
    expect(toPaise("4000.50")).toBe(400050);
    expect(toPaise("0.10") + toPaise("0.20")).toBe(30);
    expect(fromPaise(toPaise("0.10") + toPaise("0.20"))).toBe(0.3);
    expect(toPaise("not a number")).toBe(0);
  });
});

describe("invoiceAgeDays", () => {
  it("counts India days from the invoice date, never below zero", () => {
    expect(invoiceAgeDays(ago(12), TODAY)).toBe(12);
    expect(invoiceAgeDays(ago(0), TODAY)).toBe(0);
    expect(invoiceAgeDays(ago(-3), TODAY)).toBe(0);
    expect(invoiceAgeDays(null, TODAY)).toBe(0);
  });

  it("reads the day in India, not UTC", () => {
    // 20:00 UTC on the 5th is 01:30 IST on the 6th: one day old on the 7th.
    expect(invoiceAgeDays("2026-11-05T20:00:00Z", TODAY)).toBe(1);
  });
});

describe("buildFeeRows", () => {
  it("joins each charge to its client and case, and drops Rs. 0 charges", () => {
    const built = rows();
    expect(built.map((r) => r.fee.id)).not.toContain(7);
    const meera = built.find((r) => r.fee.id === 1)!;
    expect(meera.clientName).toBe("Meera Nair");
    expect(meera.caseNumber).toBe("CC/312/2026");
    expect(meera.groupKey).toBe("client:101");
    expect(meera.ageDays).toBe(12);
    expect(meera.overdue).toBe(false);
    const unlinked = built.find((r) => r.fee.id === 6)!;
    expect(unlinked.clientId).toBeNull();
    expect(unlinked.groupKey).toBe("case:13");
  });

  it("calls an invoice overdue only after 30 days", () => {
    const built = rows();
    expect(built.find((r) => r.fee.id === 3)!.overdue).toBe(true);
    const thirty = buildFeeRows([fee({ id: 9, status: "invoiced", invoiced_at: ago(30) })], CASES, TODAY)[0];
    expect(thirty.overdue).toBe(false);
    const thirtyOne = buildFeeRows([fee({ id: 9, status: "invoiced", invoiced_at: ago(31) })], CASES, TODAY)[0];
    expect(thirtyOne.overdue).toBe(true);
  });

  it("falls back to the fee's own case title when the case is not in the list", () => {
    const [row] = buildFeeRows([fee({ id: 9, case_id: 999 })], CASES, TODAY);
    expect(row.caseTitle).toBe("Meera Nair vs. Sundaram Finance Ltd");
    expect(row.groupKey).toBe("case:999");
  });
});

describe("summarize", () => {
  it("totals what is to invoice, awaiting, outstanding and paid this month", () => {
    const s = summarize(rows(), TODAY);
    expect(s.toInvoice).toEqual({ paise: 550000, count: 2 });
    expect(s.awaiting.paise).toBe(1500000 + 800000 + 400050);
    expect(s.awaiting.count).toBe(3);
    expect(s.awaiting.overdueCount).toBe(1);
    expect(s.awaiting.oldestDays).toBe(41);
    expect(s.outstanding.paise).toBe(s.toInvoice.paise + s.awaiting.paise);
    expect(s.outstanding.count).toBe(5);
    expect(s.paidThisMonth).toEqual({ paise: 600000, count: 1 });
  });

  it("leaves a payment from an earlier month out of this month's paid", () => {
    const old = buildFeeRows([fee({ id: 9, status: "paid", paid_at: "2026-09-30T06:30:00Z" })], CASES, TODAY);
    expect(summarize(old, TODAY).paidThisMonth).toEqual({ paise: 0, count: 0 });
  });
});

describe("agingBuckets", () => {
  it("puts each invoice in the server's buckets (31 and 91 start a new one)", () => {
    const edge = buildFeeRows(
      [
        fee({ id: 1, status: "invoiced", invoiced_at: ago(30), amount: "100" }),
        fee({ id: 2, status: "invoiced", invoiced_at: ago(31), amount: "200" }),
        fee({ id: 3, status: "invoiced", invoiced_at: ago(90), amount: "300" }),
        fee({ id: 4, status: "invoiced", invoiced_at: ago(91), amount: "400" }),
        fee({ id: 5, status: "pending", amount: "999" }),
      ],
      CASES,
      TODAY,
    );
    expect(agingBuckets(edge).map((b) => [b.label, b.count, b.amount])).toEqual([
      ["0-30", 1, "100.00"],
      ["31-60", 1, "200.00"],
      ["61-90", 1, "300.00"],
      ["90+", 1, "400.00"],
    ]);
  });
});

describe("filterRows", () => {
  it("filters by state", () => {
    const ids = (f: Parameters<typeof filterRows>[1]) => filterRows(rows(), f, "").map((r) => r.fee.id).sort();
    expect(ids("open")).toEqual([1, 2, 3, 4, 6]);
    expect(ids("to_invoice")).toEqual([2, 6]);
    expect(ids("awaiting")).toEqual([1, 3, 4]);
    expect(ids("paid")).toEqual([5]);
  });

  it("needs every typed word to be found in the client, case, invoice or kind", () => {
    const ids = (q: string) => filterRows(rows(), "open", q).map((r) => r.fee.id).sort();
    expect(ids("meera")).toEqual([1, 2]);
    expect(ids("rao 8841")).toEqual([3, 4]);
    expect(ids("inv-0005")).toEqual([4]);
    expect(ids("appearance")).toEqual([1, 2, 3, 4, 6]);
    expect(ids("meera rao")).toEqual([]);
    expect(ids("  ")).toEqual([1, 2, 3, 4, 6]);
  });
});

describe("groupRows", () => {
  it("puts the client with the longest-unpaid invoice first, and unpaid rows oldest first", () => {
    const groups = groupRows(filterRows(rows(), "open", ""), "open");
    expect(groups.map((g) => g.title)).toEqual(["Rao & Sons Builders", "Meera Nair", "WP/1/2026"]);
    const rao = groups[0];
    expect(rao.rows.map((r) => r.fee.id)).toEqual([3, 4]);
    expect(rao.oldestDays).toBe(41);
    expect(rao.invoiced).toHaveLength(2);
    expect(rao.unpaidPaise).toBe(800000 + 400050);
    expect(rao.subtitle).toBe("1 case");
    // Invoiced rows come before the not-yet-invoiced one.
    expect(groups[1].rows.map((r) => r.fee.id)).toEqual([1, 2]);
    // A case with no client is its own group, headed by its number.
    expect(groups[2].clientId).toBeNull();
    expect(groups[2].caseId).toBe(13);
    expect(groups[2].subtitle).toBe("Title of WP/1/2026");
  });

  it("orders the paid view by the latest payment", () => {
    const paid = buildFeeRows(
      [
        fee({ id: 1, case_id: 11, status: "paid", paid_at: ago(9), amount: "100" }),
        fee({ id: 2, case_id: 12, status: "paid", paid_at: ago(2), amount: "100" }),
      ],
      CASES,
      TODAY,
    );
    expect(groupRows(paid, "paid").map((g) => g.title)).toEqual(["Rao & Sons Builders", "Meera Nair"]);
  });
});

describe("newestPaid", () => {
  it("keeps the most recent payments", () => {
    const paid = buildFeeRows(
      [1, 2, 3].map((n) => fee({ id: n, status: "paid", paid_at: ago(n * 5) })),
      CASES,
      TODAY,
    );
    expect(newestPaid(paid, 2).map((r) => r.fee.id)).toEqual([1, 2]);
  });
});

describe("wording", () => {
  const row = (over: Partial<FeeRow>) => ({ ...rows()[0], ...over }) as FeeRow;

  it("says how long ago an invoice went out", () => {
    expect(invoicedWords(0)).toBe("Invoiced today");
    expect(invoicedWords(1)).toBe("Invoiced yesterday");
    expect(invoicedWords(12)).toBe("Invoiced 12 days ago");
  });

  it("names the state on each charge's chip", () => {
    const byId = (id: number) => rows().find((r) => r.fee.id === id)!;
    expect(feeChip(byId(2))).toEqual({ tone: "none", text: "To invoice" });
    expect(feeChip(byId(1))).toEqual({ tone: "pending", text: "Awaiting payment" });
    expect(feeChip(byId(3))).toEqual({ tone: "alert", text: "41 days unpaid" });
    expect(feeChip(byId(5))).toEqual({ tone: "ok", text: "Paid" });
  });

  it("does not repeat the case number a title already starts with", () => {
    expect(caseLabel(row({ caseNumber: "WP/1/2026", caseTitle: "WP/1/2026 Rao vs State" }))).toBe("WP/1/2026 Rao vs State");
    expect(caseLabel(row({ caseNumber: "WP/1/2026", caseTitle: "Rao vs State" }))).toBe("WP/1/2026 · Rao vs State");
    expect(caseLabel(row({ caseNumber: "", caseTitle: "Rao vs State" }))).toBe("Rao vs State");
  });
});
