import type { Page } from "@playwright/test";
import { CASE_ID, caseDetail, documents, events, hearings as caseHearings, orders } from "./fixtures";

/** A small practice -- six cases, hearings across the week, tasks, bills --
 * for the mobile specs. Everything the dashboard, Cases, Calendar and Billing
 * screens ask for is answered here, in the browser, so no backend is needed.
 * Dates hang off today so "tomorrow" stays tomorrow. Placeholder data. */

const DAY = 86_400_000;
// The app shows India dates, so "today" here is the India date too (between 18:30 and 24:00 UTC
// the UTC date is still yesterday, and every "Tomorrow" in the specs would be off by one).
const IST_OFFSET = 330 * 60_000;
const iso = (offset: number) => new Date(Date.now() + IST_OFFSET + offset * DAY).toISOString().slice(0, 10);
const midnightUtc = (offset: number) => `${iso(offset)}T00:00:00Z`;

const TITLES: [string, string, string][] = [
  ["Butham Srinivas vs. State of Telangana", "WP/1709/2026", "Telangana High Court"],
  ["Meera Nair vs. Sundaram Finance Ltd", "CC/312/2026", "XII Addl. Chief Metropolitan Magistrate, Hyderabad"],
  ["Rao & Sons Builders vs. GHMC", "WP/8841/2025", "Telangana High Court"],
  ["Kavitha Reddy vs. Ramesh Reddy", "FC/118/2025", "Family Court, Secunderabad"],
  ["State of Telangana vs. Imran Sheikh", "CRL/2290/2025", "Metropolitan Sessions Judge, Hyderabad"],
  ["Anand Textiles vs. Union of India", "WP/1120/2026", "Telangana High Court"],
];

const feeSummary = {
  pending_amount: "0",
  pending_count: 0,
  invoiced_amount: "0",
  invoiced_count: 0,
  paid_amount: "0",
  paid_count: 0,
  outstanding_amount: "0",
  total_amount: "0",
};

// The shared fixture's event date is a UTC date; re-date it on the India day like everything here.
const mobileEvents = events.map((e) => ({ ...e, date: iso(7) }));

export const mobileCases = TITLES.map(([title, number, court], i) => ({
  ...caseDetail,
  id: i === 0 ? CASE_ID : 10 + i,
  title,
  case_number: number,
  client_name: title.split(" vs.")[0],
  client_detail: { id: 100 + i, name: title.split(" vs.")[0], client_type: "individual" },
  priority: (["medium", "high", "medium", "low", "critical", "medium"] as const)[i],
  needs_attention: i < 3,
  next_hearing_date: i === 5 ? null : midnightUtc([0, 1, 4, 9, 2, 0][i]),
  tracking_snapshot: { ...caseDetail.tracking_snapshot, court_name: court, next_hearing_date: iso([0, 1, 4, 9, 2, 0][i]) },
  fee_summary: i === 1 ? { ...feeSummary, invoiced_amount: "15000", invoiced_count: 1, outstanding_amount: "15000" } : feeSummary,
  parties: { ...caseDetail.parties, petitioner: title.split(" vs.")[0], respondent: title.split("vs. ")[1] },
  order_sync: i === 3 ? { ...caseDetail.order_sync, state: "failed", reason: "court portal didn't answer" } : caseDetail.order_sync,
}));

const hearing = (id: number, caseIdx: number, offset: number, extra: Record<string, unknown> = {}) => ({
  ...caseHearings[0],
  id,
  case: mobileCases[caseIdx].id,
  case_title: mobileCases[caseIdx].title,
  hearing_date: `${iso(offset)}T04:30:00Z`,
  location: TITLES[caseIdx][2],
  status: "scheduled",
  status_display: "Scheduled",
  purpose: "Arguments",
  cause_list_status: "listed",
  cause_list_status_display: "Listed",
  cause_list_item_number: String(10 + id),
  cause_list_court_hall: "Court 7",
  ...extra,
});

export const mobileHearings = [
  hearing(101, 0, 0, { cause_list_item_number: "14", purpose: "Hearing on interim application" }),
  hearing(102, 5, 0, { cause_list_status: "not_published", cause_list_item_number: "", cause_list_court_hall: "", purpose: "Final hearing" }),
  hearing(103, 1, 1, { cause_list_status: "not_published", cause_list_item_number: "", purpose: "Cross-examination of PW-2" }),
  hearing(104, 4, 2, { purpose: "Bail application" }),
  hearing(105, 2, 4, { cause_list_status: "not_checked", purpose: "Counter affidavit" }),
  hearing(106, 3, 9, { cause_list_status: "unsupported", purpose: "Mediation report" }),
  hearing(107, 0, -6, { status: "completed", status_display: "Completed", outcome: "Adjourned for counter" }),
];

const task = (id: number, caseIdx: number | null, title: string, due: number | null, extra: Record<string, unknown> = {}) => ({
  id,
  case: caseIdx === null ? null : mobileCases[caseIdx].id,
  case_title: caseIdx === null ? null : mobileCases[caseIdx].title,
  case_number: caseIdx === null ? null : mobileCases[caseIdx].case_number,
  title,
  description: null,
  status: "pending",
  kind: "manual",
  kind_display: "Manual",
  due_date: due === null ? null : iso(due),
  due_date_basis: "",
  due_date_basis_display: "",
  source_order: null,
  source_text: "",
  rule_key: "",
  trigger_date: null,
  needs_review: false,
  user_modified: false,
  completed_at: null,
  created_at: midnightUtc(-5),
  updated_at: midnightUtc(-5),
  ...extra,
});

export const mobileTasks = [
  task(1, 1, "File counter affidavit", -2),
  task(2, 0, "Collect certified copy of the order", 1),
  task(3, 4, "Prepare bail grounds note", 2, { kind: "order_direction", kind_display: "Order direction", needs_review: true }),
  task(4, null, "Renew bar council registration", 12),
];

const billing = {
  as_of: iso(0),
  aging: [
    { label: "0-30", count: 1, amount: "15000" },
    { label: "31-60", count: 1, amount: "8000" },
    { label: "61-90", count: 0, amount: "0" },
    { label: "90+", count: 0, amount: "0" },
  ],
  totals: { invoiced_amount: "23000", invoiced_count: 2, pending_amount: "12000", pending_count: 2 },
  clients: [
    { client_id: 101, client_name: "Meera Nair", client_type: "individual", case_count: 1, invoiced_amount: "15000", invoiced_count: 1, pending_amount: "0", pending_count: 0, oldest_invoice_days: 12 },
    { client_id: 102, client_name: "Rao & Sons Builders", client_type: "business", case_count: 1, invoiced_amount: "8000", invoiced_count: 1, pending_amount: "12000", pending_count: 2, oldest_invoice_days: 41 },
  ],
  clients_total: 2,
  unassigned: [],
  unassigned_total: 0,
  uninvoiced_hearings: [
    { hearing_id: 107, hearing_date: midnightUtc(-6), case_id: CASE_ID, case_title: TITLES[0][0], case_number: TITLES[0][1], pending_amount: "5000", has_fee: true },
  ],
  uninvoiced_hearings_total: 1,
};

/** Answers every API call the mobile screens make, in the browser. */
export async function mockMobileApi(page: Page, overrides: Record<string, unknown> = {}): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem("case_intel_token", "e2e-token");
    window.localStorage.setItem("case_intel_username", "e2e");
  });
  await page.route("http://localhost:8000/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const headers = { "access-control-allow-origin": "*", "access-control-allow-headers": "*" };
    const body = (data: unknown) =>
      route.fulfill({ status: 200, contentType: "application/json", headers, body: JSON.stringify(data) });
    if (route.request().method() === "OPTIONS") {
      return route.fulfill({ status: 204, headers: { ...headers, "access-control-allow-methods": "*" } });
    }
    if (path in overrides) return body(overrides[path]);
    if (path === "/cases/") return body(mobileCases);
    if (path === `/cases/${CASE_ID}/`) return body(mobileCases[0]);
    if (path === `/cases/${CASE_ID}/orders/`) return body(orders);
    const m = path.match(/^\/cases\/(\d+)\/$/);
    if (m) return body(mobileCases.find((c) => c.id === Number(m[1])) ?? mobileCases[0]);
    if (path === "/hearings/") {
      const caseId = url.searchParams.get("case_id");
      if (caseId && Number(caseId) === CASE_ID) return body([...mobileHearings.filter((h) => h.case === CASE_ID), ...caseHearings]);
      return body(caseId ? mobileHearings.filter((h) => h.case === Number(caseId)) : mobileHearings);
    }
    if (path === "/dashboard/upcoming-hearings/") {
      return body(
        mobileHearings
          .filter((h) => h.status === "scheduled")
          .map((h) => ({
            id: h.id,
            case_id: h.case,
            case_title: h.case_title,
            case_number: mobileCases.find((c) => c.id === h.case)?.case_number ?? "",
            hearing_date: h.hearing_date,
            hearing_type: "other",
            hearing_type_display: "Other",
            judge: null,
            purpose: h.purpose,
            source: "ecourts",
            status: "scheduled",
            days_until: Math.round((Date.parse(h.hearing_date) - Date.now()) / DAY),
            updated_at: midnightUtc(-1),
          })),
      );
    }
    if (path === "/tasks/") return body(mobileTasks);
    if (path === "/documents/") return body(documents);
    if (path === "/case-events/") return body(mobileEvents);
    if (path === "/billing/portfolio/") return body(billing);
    if (path === "/advocate-profile/") return body({ advocate_name: "Bhagath Kumar", contact_email: "e2e@example.com", default_fee_amount: "5000" });
    if (path === "/cases/refresh-all/") return body({ job_id: null });
    return body([]);
  });
}
