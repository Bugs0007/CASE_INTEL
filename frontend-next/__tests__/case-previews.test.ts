import { describe, it, expect } from "vitest";
import {
  dayCellSummary,
  expandedTasks,
  flattenFees,
  latestOrderDocument,
  latestOrderForOverview,
  matchesQuery,
  nextHearing,
  ordersWithOverview,
  previewContacts,
  previewDocuments,
  previewFees,
  previewHearings,
  previewTasks,
  showSearch,
  sortOpenTasks,
  splitHearings,
} from "@/lib/case-previews";
import type {
  ClientContact,
  CourtOrder,
  Document,
  Hearing,
  NestedAppearanceFee,
  Task,
} from "@/types";

const TODAY = "2026-11-10";
const NOW = new Date("2026-11-10T06:00:00Z");

function task(id: number, overrides: Partial<Task> = {}): Task {
  return {
    id,
    case: 1,
    title: `Task ${id}`,
    status: "pending",
    kind: "manual",
    due_date: null,
    completed_at: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    ...overrides,
  } as Task;
}

describe("previewTasks", () => {
  it("lists overdue first, then soonest due, then undated, capped at 3", () => {
    const tasks = [
      task(1, { due_date: "2026-11-20" }),
      task(2, { due_date: "2026-11-12" }),
      task(3), // undated
      task(4, { due_date: "2026-11-05" }), // overdue
      task(5, { due_date: "2026-11-08" }), // overdue
      task(6, { due_date: "2026-11-10" }), // due today is not overdue
    ];
    expect(previewTasks(tasks, 3, TODAY).map((t) => t.id)).toEqual([4, 5, 6]);
    expect(sortOpenTasks(tasks, TODAY).map((t) => t.id)).toEqual([4, 5, 6, 2, 1, 3]);
  });

  it("never previews a completed or dismissed task", () => {
    const tasks = [
      task(1, { status: "completed", due_date: "2026-11-01" }),
      task(2, { status: "cancelled", due_date: "2026-11-02" }),
      task(3, { status: "in_progress", due_date: "2026-11-30" }),
    ];
    expect(previewTasks(tasks, 3, TODAY).map((t) => t.id)).toEqual([3]);
  });

  it("puts closed tasks only in the expanded view, newest first", () => {
    const tasks = [
      task(1, { due_date: "2026-11-12" }),
      task(2, { status: "completed", completed_at: "2026-11-03T00:00:00Z" }),
      task(3, { status: "cancelled", completed_at: null, updated_at: "2026-11-08T00:00:00Z" }),
    ];
    const { open, closed } = expandedTasks(tasks, TODAY);
    expect(open.map((t) => t.id)).toEqual([1]);
    expect(closed.map((t) => t.id)).toEqual([3, 2]);
  });

  it("handles a case with no tasks", () => {
    expect(previewTasks([], 3, TODAY)).toEqual([]);
    expect(expandedTasks([], TODAY)).toEqual({ open: [], closed: [] });
  });
});

function hearing(id: number, date: string, overrides: Partial<Hearing> = {}): Hearing {
  return {
    id,
    hearing_date: `${date}T00:00:00Z`,
    status: "scheduled",
    appearance_fees: [],
    ...overrides,
  } as Hearing;
}

describe("previewHearings", () => {
  const hearings = [
    hearing(1, "2026-09-01", { status: "completed" }),
    hearing(2, "2026-10-01", { status: "completed" }),
    hearing(3, "2026-10-20", { status: "completed" }),
    hearing(4, "2026-11-20"),
    hearing(5, "2026-12-15"),
    hearing(6, "2026-11-01"), // date passed but still "scheduled": awaiting update
  ];

  it("takes the next upcoming hearing and the 2 most recent past ones", () => {
    const { next, recent } = previewHearings(hearings, NOW);
    expect(next?.id).toBe(4);
    expect(recent.map((h) => h.id)).toEqual([6, 3]);
  });

  it("treats a cancelled future hearing as past, not as the next one", () => {
    const list = [hearing(1, "2026-11-15", { status: "cancelled" }), hearing(2, "2026-11-25")];
    expect(nextHearing(list, NOW)?.id).toBe(2);
    expect(splitHearings(list, NOW).past.map((h) => h.id)).toEqual([1]);
  });

  it("does not depend on the order the API returned them in", () => {
    const shuffled = [...hearings].reverse();
    expect(previewHearings(shuffled, NOW).next?.id).toBe(4);
    expect(splitHearings(shuffled, NOW).upcoming.map((h) => h.id)).toEqual([4, 5]);
  });

  it("copes with no upcoming hearing and with no hearings at all", () => {
    expect(previewHearings([hearing(1, "2026-09-01", { status: "completed" })], NOW)).toEqual({
      next: null,
      recent: [expect.objectContaining({ id: 1 })],
    });
    expect(previewHearings([], NOW)).toEqual({ next: null, recent: [] });
  });
});

function doc(id: number, overrides: Partial<Document> = {}): Document {
  return {
    id,
    filename: `doc-${id}.pdf`,
    document_type: "pleading",
    document_date: null,
    created_at: `2026-10-${String(id).padStart(2, "0")}T00:00:00Z`,
    ...overrides,
  } as Document;
}

describe("previewDocuments", () => {
  it("pins the latest order first, then the newest uploads, capped at 4", () => {
    const docs = [
      doc(1, { document_type: "court_order", document_date: "2026-09-01" }),
      doc(2, { document_type: "court_order", document_date: "2026-10-15" }), // latest order
      doc(3),
      doc(4),
      doc(5),
      doc(6),
    ];
    expect(latestOrderDocument(docs)?.id).toBe(2);
    expect(previewDocuments(docs).map((d) => d.id)).toEqual([2, 6, 5, 4]);
  });

  it("falls back to the upload date when an order document has no date", () => {
    const docs = [
      doc(1, { document_type: "court_order" }),
      doc(9, { document_type: "court_order" }),
    ];
    expect(latestOrderDocument(docs)?.id).toBe(9);
  });

  it("is just newest-first when there is no order", () => {
    expect(previewDocuments([doc(1), doc(3), doc(2)]).map((d) => d.id)).toEqual([3, 2, 1]);
    expect(previewDocuments([])).toEqual([]);
  });
});

function fee(id: number, status: NestedAppearanceFee["status"], paidAt: string | null = null) {
  return { id, status, paid_at: paidAt } as NestedAppearanceFee;
}

describe("previewFees", () => {
  const hearings = [
    hearing(1, "2026-08-01", { appearance_fees: [fee(10, "paid", "2026-09-01T00:00:00Z")] }),
    hearing(2, "2026-09-01", { appearance_fees: [fee(11, "invoiced"), fee(12, "pending")] }),
    hearing(3, "2026-10-01", {
      appearance_fees: [fee(13, "paid", "2026-10-20T00:00:00Z"), fee(14, "pending")],
    }),
  ];

  it("lists unpaid first (longest outstanding first), then the latest paid", () => {
    const all = flattenFees(hearings);
    expect(all).toHaveLength(5);
    expect(previewFees(all).map((x) => x.fee.id)).toEqual([11, 12, 14]);
    expect(previewFees(all, 5).map((x) => x.fee.id)).toEqual([11, 12, 14, 13, 10]);
  });

  it("shows a paid fee when nothing is unpaid", () => {
    const paidOnly = flattenFees([hearings[0], hearings[2]].map((h) => ({ ...h, appearance_fees: h.appearance_fees.filter((f) => f.status === "paid") })));
    expect(previewFees(paidOnly).map((x) => x.fee.id)).toEqual([13, 10]);
  });

  it("is empty for hearings without charges", () => {
    expect(previewFees(flattenFees([hearing(1, "2026-08-01")]))).toEqual([]);
  });
});

function contact(id: number, overrides: Partial<ClientContact> = {}): ClientContact {
  return { id, name: `C${id}`, role: "assistant", is_billing_contact: false, ...overrides } as ClientContact;
}

describe("previewContacts", () => {
  it("puts the primary then the billing contact first, max 2", () => {
    const contacts = [
      contact(1),
      contact(2, { is_billing_contact: true }),
      contact(3, { role: "primary" }),
    ];
    expect(previewContacts(contacts).map((c) => c.id)).toEqual([3, 2]);
  });

  it("counts one person who is both only once", () => {
    const contacts = [contact(1), contact(2, { role: "primary", is_billing_contact: true }), contact(3)];
    expect(previewContacts(contacts).map((c) => c.id)).toEqual([2, 1]);
  });

  it("keeps API order for the rest and handles none", () => {
    expect(previewContacts([contact(5), contact(4)], 5).map((c) => c.id)).toEqual([5, 4]);
    expect(previewContacts([])).toEqual([]);
  });
});

describe("dayCellSummary", () => {
  it("shows up to 2 items with nothing hidden", () => {
    expect(dayCellSummary([1, 2])).toEqual({ visible: [1, 2], hidden: 0 });
    expect(dayCellSummary([1])).toEqual({ visible: [1], hidden: 0 });
    expect(dayCellSummary(undefined)).toEqual({ visible: [], hidden: 0 });
  });

  it("counts the rest as '+n more' when there are more than 2", () => {
    expect(dayCellSummary([1, 2, 3])).toEqual({ visible: [1, 2], hidden: 1 });
    expect(dayCellSummary([1, 2, 3, 4, 5])).toEqual({ visible: [1, 2], hidden: 3 });
  });
});

function order(id: number, date: string | null, status: string = "summarized"): CourtOrder {
  return { id, order_date: date, summary: { status } } as unknown as CourtOrder;
}

describe("order overviews", () => {
  it("the card uses the latest DATED order, even when it has no summary yet", () => {
    const orders = [order(1, "2026-08-01"), order(2, "2026-10-01", "pending"), order(3, null)];
    expect(latestOrderForOverview(orders)?.id).toBe(2);
    expect(latestOrderForOverview([order(3, null)])).toBeNull();
  });

  it("the dialog lists every summarised order, newest first, undated last", () => {
    const orders = [
      order(1, "2026-08-01"),
      order(2, "2026-10-01"),
      order(3, null),
      order(4, "2026-09-01", "pending"),
      order(5, "2026-10-01"),
    ];
    expect(ordersWithOverview(orders).map((o) => o.id)).toEqual([5, 2, 1, 3]);
  });
});

describe("search", () => {
  it("only offers search for more than 8 items", () => {
    expect(showSearch(8)).toBe(false);
    expect(showSearch(9)).toBe(true);
  });

  it("matches every word, case-insensitively, across fields", () => {
    expect(matchesQuery("", "anything")).toBe(true);
    expect(matchesQuery("  ", null)).toBe(true);
    expect(matchesQuery("vakalat cert", "Certified copy", "vakalatnama")).toBe(true);
    expect(matchesQuery("vakalat missing", "Certified copy", "vakalatnama")).toBe(false);
  });
});
