import { describe, expect, it } from "vitest";
import {
  draftCounts,
  filterDrafts,
  filterSent,
  messageCaseLabel,
  messagePreview,
  recipientNames,
  sentCounts,
} from "@/lib/messages-model";
import type { ClientMessage, SentMessage } from "@/types";

function draft(over: Partial<ClientMessage> & { id: number }): ClientMessage {
  return {
    case: 3,
    case_title: "Rao vs Reddy",
    case_number: "OS/10/2026",
    kind: "case_update",
    kind_display: "Case update",
    status: "draft",
    status_display: "Draft",
    subject: "Update on your matter",
    body: "Dear Client One,\n\nThe matter was heard on 01 September 2026.",
    recipients: [{ contact_id: 9, name: "Client One", email: "one@example.com" }],
    eligible_recipients: [],
    invoice_number: null,
    ...over,
  } as ClientMessage;
}

function sentRow(over: Partial<SentMessage> & { id: number }): SentMessage {
  return {
    subject: "Update on your matter",
    kind: "case_update",
    kind_display: "Case update",
    delivery: "sent",
    to_emails: ["one@example.com"],
    case_number: "OS/10/2026",
    case_title: "Rao vs Reddy",
    ...over,
  } as SentMessage;
}

describe("messagePreview", () => {
  it("skips the salutation and gives the first words of what it says", () => {
    expect(messagePreview("Dear Client One,\n\nThe matter was heard on 01 September 2026.\nNext date 5 Oct.")).toBe(
      "The matter was heard on 01 September 2026. Next date 5 Oct.",
    );
  });

  it("cuts a long message at the limit with an ellipsis", () => {
    const text = messagePreview(`Hello,\n${"word ".repeat(60)}`, 40);
    expect(text.length).toBeLessThanOrEqual(40);
    expect(text.endsWith("…")).toBe(true);
  });

  it("keeps a body that is only a salutation, and an empty one empty", () => {
    expect(messagePreview("Dear Sir,")).toBe("Dear Sir,");
    expect(messagePreview("")).toBe("");
  });
});

describe("who and which case", () => {
  it("names the recipients, falling back to the address", () => {
    expect(
      recipientNames({
        recipients: [
          { contact_id: 1, name: "Meera Nair", email: "m@example.com" },
          { contact_id: 2, name: "", email: "x@example.com" },
        ],
      }),
    ).toBe("Meera Nair, x@example.com");
    expect(recipientNames({ recipients: [] })).toBe("");
  });

  it("does not repeat a case number the title starts with", () => {
    expect(messageCaseLabel({ case_number: "OS/10/2026", case_title: "OS/10/2026 Rao vs Reddy" })).toBe("OS/10/2026 Rao vs Reddy");
    expect(messageCaseLabel({ case_number: "OS/10/2026", case_title: "Rao vs Reddy" })).toBe("OS/10/2026 · Rao vs Reddy");
  });
});

describe("drafts", () => {
  const drafts = [
    draft({ id: 1 }),
    draft({ id: 2, kind: "payment_reminder", kind_display: "Payment reminder", subject: "Reminder: invoice INV-0007", invoice_number: "INV-0007" }),
    draft({ id: 3, case_number: "WP/1/2026", case_title: "Meera vs State", recipients: [{ contact_id: 4, name: "Meera Nair", email: "m@example.com" }] }),
  ];

  it("counts by kind", () => {
    expect(draftCounts(drafts)).toEqual({ all: 3, case_update: 2, payment_reminder: 1 });
  });

  it("filters by kind and by every typed word", () => {
    const ids = (kind: Parameters<typeof filterDrafts>[1], q = "") => filterDrafts(drafts, kind, q).map((m) => m.id);
    expect(ids("all")).toEqual([1, 2, 3]);
    expect(ids("payment_reminder")).toEqual([2]);
    expect(ids("all", "meera")).toEqual([3]);
    expect(ids("all", "inv-0007")).toEqual([2]);
    expect(ids("case_update", "reminder")).toEqual([]);
  });
});

describe("sent log", () => {
  const rows = [
    sentRow({ id: 1 }),
    sentRow({ id: 2, delivery: "logged", subject: "Invoice INV-0003", kind: "invoice", kind_display: "Invoice", to_emails: ["rao@example.com"] }),
  ];

  it("counts and filters emailed against logged-only", () => {
    expect(sentCounts(rows)).toEqual({ all: 2, sent: 1, logged: 1 });
    expect(filterSent(rows, "logged", "").map((r) => r.id)).toEqual([2]);
    expect(filterSent(rows, "sent", "").map((r) => r.id)).toEqual([1]);
    expect(filterSent(rows, "all", "rao@example.com").map((r) => r.id)).toEqual([2]);
  });
});
