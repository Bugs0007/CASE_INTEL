import type { Page } from "@playwright/test";
import { mobileCases } from "./mobile-fixtures";

/** Charges and client messages for the Billing and Messages specs, on the
 * same six cases as mobile-fixtures.ts (case index 1 is Meera Nair, client
 * 101; index 2 is Rao & Sons Builders, client 102). Dates hang off now, so
 * "12 days ago" stays 12 days. Placeholder data. */

const DAY = 86_400_000;
const ago = (days: number) => new Date(Date.now() - days * DAY).toISOString();

const CORS = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" };

function fee(id: number, caseIdx: number, over: Record<string, unknown>) {
  const kase = mobileCases[caseIdx];
  return {
    id,
    hearing: 200 + id,
    case_id: kase.id,
    case_title: kase.title,
    hearing_date: "2026-10-12T00:00:00Z",
    category: "appearance",
    category_display: "Appearance Fee",
    amount: "5000.00",
    status: "pending",
    status_display: "Pending",
    invoice_number: "",
    invoice_sequence: null,
    invoiced_at: null,
    paid_at: null,
    sent_at: null,
    sent_to_email: "",
    send_status: "not_sent",
    notes: "",
    created_at: ago(30),
    updated_at: ago(1),
    ...over,
  };
}

export const billingFees = [
  // Meera Nair: one invoice out for 12 days, one charge not yet invoiced.
  fee(1, 1, { status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0007", invoiced_at: ago(12), amount: "15000.00", send_status: "sent" }),
  fee(2, 1, { amount: "3000.00" }),
  // Rao & Sons Builders: two invoices, one of them 41 days old.
  fee(3, 2, { status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0003", invoiced_at: ago(41), amount: "8000.00" }),
  fee(4, 2, { status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0005", invoiced_at: ago(5), amount: "4000.00", send_status: "sent" }),
  // Settled earlier today.
  fee(5, 1, { status: "paid", status_display: "Paid", invoice_number: "INV-0001", invoiced_at: ago(40), paid_at: ago(0), amount: "6000.00", send_status: "sent" }),
];

export interface FeeApiLog {
  /** "POST mark-paid 1", "POST invoice 2" ... in the order they arrived. */
  calls: string[];
}

/** Answers /appearance-fees/ (and its mark-paid / invoice actions) with a
 * list that changes as the page acts on it, the way the server's does. Call
 * AFTER mockMobileApi: a later route wins. */
export async function mockFeeApi(page: Page, fees: Record<string, unknown>[] = billingFees): Promise<FeeApiLog> {
  const state = fees.map((f) => ({ ...f }));
  const log: FeeApiLog = { calls: [] };
  await page.route("http://localhost:8000/api/appearance-fees/**", async (route) => {
    const request = route.request();
    const { pathname } = new URL(request.url());
    const json = (status: number, data: unknown) =>
      route.fulfill({ status, contentType: "application/json", headers: CORS, body: JSON.stringify(data) });
    if (request.method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { ...CORS, "access-control-allow-methods": "*" } });
    }
    const action = pathname.match(/\/appearance-fees\/(\d+)\/(mark-paid|invoice)\/$/);
    if (action && request.method() === "POST") {
      const found = state.find((f) => f.id === Number(action[1]));
      log.calls.push(`POST ${action[2]} ${action[1]}`);
      if (!found) return json(404, { detail: "Appearance fee not found." });
      if (action[2] === "mark-paid") {
        if (found.status !== "invoiced") {
          return json(409, { detail: found.status === "paid" ? "This fee is already marked paid." : "This fee has not been invoiced yet. Generate the invoice before marking it paid." });
        }
        Object.assign(found, { status: "paid", status_display: "Paid", paid_at: new Date().toISOString() });
      } else {
        Object.assign(found, { status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0009", invoiced_at: new Date().toISOString() });
      }
      return json(200, found);
    }
    return json(200, state);
  });
  return log;
}

const contact = { contact_id: 9, name: "Meera Nair", email: "meera@example.com" };

function draft(id: number, over: Record<string, unknown>) {
  const kase = mobileCases[1];
  return {
    id,
    case: kase.id,
    case_title: kase.title,
    case_number: kase.case_number,
    kind: "case_update",
    kind_display: "Case update",
    status: "draft",
    status_display: "Draft",
    subject: "Update on your matter",
    body: "Dear Meera Nair,\n\nYour matter was heard today and has been adjourned for cross-examination.",
    recipients: [contact],
    eligible_recipients: [contact],
    edited_by_user: false,
    reminder_number: null,
    fee: null,
    invoice_number: null,
    hearing: null,
    hearing_date: null,
    event_date: null,
    court_order: null,
    sent_at: null,
    discard_reason: "",
    created_at: ago(2),
    updated_at: ago(2),
    ...over,
  };
}

export const messageDrafts = [
  draft(1, {}),
  draft(2, {
    kind: "payment_reminder",
    kind_display: "Payment reminder",
    subject: "Reminder: invoice INV-0007 is unpaid",
    body: "Dear Rao,\n\nInvoice INV-0007 for Rs. 15,000 is still awaiting payment.",
    case: mobileCases[2].id,
    case_title: mobileCases[2].title,
    case_number: mobileCases[2].case_number,
    recipients: [{ contact_id: 4, name: "Rao & Sons Builders", email: "rao@example.com" }],
    eligible_recipients: [{ contact_id: 4, name: "Rao & Sons Builders", email: "rao@example.com" }],
    invoice_number: "INV-0007",
    created_at: ago(5),
  }),
  draft(3, {
    subject: "Hearing update with nobody to send it to",
    case: mobileCases[3].id,
    case_title: mobileCases[3].title,
    case_number: mobileCases[3].case_number,
    recipients: [],
    eligible_recipients: [],
  }),
];

export const sentMessages = [
  { id: 1, sent_at: ago(1), sent_by: 1, sent_by_username: "e2e", kind: "case_update", kind_display: "Case update", delivery: "sent", delivery_display: "Sent", to_emails: ["meera@example.com"], cc_emails: [], subject: "Update on your matter", body_sha256: "a", case: mobileCases[1].id, case_title: mobileCases[1].title, case_number: mobileCases[1].case_number, message: null, fee: null },
  { id: 2, sent_at: ago(3), sent_by: 1, sent_by_username: "e2e", kind: "invoice", kind_display: "Invoice", delivery: "logged", delivery_display: "Logged", to_emails: ["rao@example.com"], cc_emails: [], subject: "Invoice INV-0003", body_sha256: "b", case: mobileCases[2].id, case_title: mobileCases[2].title, case_number: mobileCases[2].case_number, message: null, fee: 3 },
];
