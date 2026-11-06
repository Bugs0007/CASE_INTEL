import type { Page } from "@playwright/test";

/** A realistic case for the e2e specs, plus the API routes that serve it.
 * Dates are built from today so "in 14 days" stays true. Placeholder data. */

const DAY = 86_400_000;
const iso = (offsetDays: number) => new Date(Date.now() + offsetDays * DAY).toISOString().slice(0, 10);
const midnightUtc = (offsetDays: number) => `${iso(offsetDays)}T00:00:00Z`;

export const CASE_ID = 1;

const summary = {
  status: "summarized",
  status_display: "Summarised",
  route: "llm",
  what_happened:
    "The court gave an interim direction to respondent No.2 to consider the petitioner's representations for inclusion of his name in the voters' list. The matter is listed on 10.02.2026.",
  petitioner_directions: [],
  respondent_directions: [
    "consider the representations of the petitioner dated 05.01.2026 and 12.01.2026 for inclusion of his name in the voters' list of Ward No.36 of Adilabad Municipality, within a period of seven (7) days from the date of receipt of a copy of this order",
  ],
  your_side_directions: null,
  other_side_directions: null,
  your_side_label: null,
  other_side_label: null,
  party_role: "unknown",
  next_date: "2026-02-10",
  next_date_purpose: "",
  is_routine_adjournment: false,
  generated_at: null,
  error: "",
};

const hearing = (id: number, offset: number, status: string, extra: Record<string, unknown> = {}) => ({
  id,
  case: CASE_ID,
  case_title: "Butham Srinivas vs. Respondent (Adilabad)",
  hearing_date: midnightUtc(offset),
  hearing_type: "other",
  hearing_type_display: "Other",
  location: "Telangana High Court",
  judge: null,
  status,
  status_display: status,
  notes: null,
  outcome: null,
  source: "ecourts",
  business_date: null,
  purpose: null,
  appearance_fees: [],
  travel_bookings: [],
  cause_list_status: "not_checked",
  cause_list_status_display: "",
  cause_list_item_number: "",
  cause_list_court_hall: "",
  cause_list_stage: "",
  cause_list_checked_at: null,
  order_summary: null,
  created_at: midnightUtc(-200),
  updated_at: midnightUtc(-1),
  ...extra,
});

export const hearings = [
  hearing(1, 14, "scheduled", { cause_list_status: "not_published" }),
  hearing(2, -268, "scheduled", { outcome: "Date given in the order of 20 Jan 2026" }),
  hearing(3, -290, "completed", { outcome: "Interim direction to respondent No.2" }),
  hearing(4, -300, "completed", { outcome: "Listed for admission" }),
  hearing(5, -310, "completed", { outcome: "Registered and numbered" }),
  hearing(6, -350, "completed", { outcome: "Filed, under scrutiny" }),
  hearing(7, -380, "completed", { outcome: "Notice ordered to respondents" }),
];

const order = (id: number, offset: number, withSummary: boolean) => ({
  id,
  order_number: String(id),
  order_date: iso(offset),
  description: "",
  judge: "",
  source: "ecourts",
  has_file: true,
  download_status: "downloaded",
  filename: `order_${iso(offset)}.pdf`,
  file_size: 20_000,
  processing_status: "completed",
  summary: withSummary ? { ...summary, next_date: iso(-268) } : { ...summary, status: "pending" },
  created_at: midnightUtc(-1),
});

export const orders = [order(1, -290, true), order(2, -380, true)];

const doc = (id: number, name: string, type: string, offset: number) => ({
  id,
  case_id: CASE_ID,
  filename: name,
  display_name: name,
  file_path: name,
  file_type: "application/pdf",
  file_size: 20_000,
  document_type: type,
  document_date: iso(offset),
  processing_status: "completed",
  chunk_count: 3,
  ocr_applied: false,
  job_status: null,
  job_progress_current: null,
  job_progress_total: null,
  job_error: null,
  created_at: midnightUtc(offset),
  case: { id: CASE_ID, title: "Butham Srinivas vs. Respondent (Adilabad)", case_number: "WP/1709/2026" },
});

export const documents = [
  doc(1, "order_2026-01-20.pdf", "court_order", -290),
  doc(2, "representation_12-01-2026.pdf", "pleading", -298),
  doc(3, "representation_05-01-2026.pdf", "pleading", -305),
  doc(4, "writ_petition.pdf", "pleading", -330),
  doc(5, "notice_20-11-2025.pdf", "court_order", -380),
  doc(6, "vakalatnama.pdf", "other", -340),
];

export const caseDetail = {
  id: CASE_ID,
  case_number: "WP/1709/2026",
  title: "Butham Srinivas vs. Respondent (Adilabad)",
  client_name: "Butham Srinivas",
  client: null,
  client_detail: { id: 1, name: "Butham Srinivas", client_type: "individual" },
  client_contacts: [],
  opposing_party: null,
  user_party_role: "unknown",
  case_type: "civil",
  status: "open",
  priority: "medium",
  filing_date: "2026-08-14",
  notes: null,
  created_at: midnightUtc(-200),
  document_count: documents.length,
  hearing_count: hearings.length,
  thread_count: 0,
  conversation_count: 0,
  cnr_number: "HBHC010234562026",
  court_type: "high_court",
  tracking_config: { cnr: "HBHC010234562026", court_type: "high_court" },
  tracking_enabled: true,
  fetch_status: "success",
  last_fetched_at: new Date(Date.now() - 2 * 3_600_000).toISOString(),
  needs_attention: false,
  next_hearing_date: midnightUtc(14),
  fee_summary: {
    pending_amount: "0",
    pending_count: 0,
    invoiced_amount: "0",
    invoiced_count: 0,
    paid_amount: "0",
    paid_count: 0,
    outstanding_amount: "0",
    total_amount: "0",
  },
  order_sync: { state: "ok", last_checked_at: new Date().toISOString(), last_success_at: new Date().toISOString(), found: 2, downloaded: 2, reason: null },
  tracking_snapshot: {
    case_status: "Pending",
    case_stage: "Interim order passed",
    court_and_judge: null,
    court_name: "Telangana High Court",
    nature_of_disposal: null,
    next_hearing_date: iso(14),
  },
  tracking_freshness: { stale: false, reasons: [], stale_after_days: 7, awaiting_update_count: 0, refresh_available_at: null },
  cause_list_coverage: { status: "supported", label: "Telangana High Court", reason: "", url: "" },
  disposal: null,
  update_recipient_count: 0,
  parties: { petitioner: "Butham Srinivas", respondent: "State", source: "title", ours: "", opposing: "" },
};

export const events = [
  { id: 1, case: CASE_ID, title: "Client call", date: iso(7), start_time: null, end_time: null, status: "scheduled", event_type: "client_call", notes: "", location: "" },
];

/** Answers every API call the case page makes, in the browser. */
export async function mockApi(page: Page, overrides: Record<string, unknown> = {}): Promise<void> {
  await page.addInitScript(() => {
    window.localStorage.setItem("case_intel_token", "e2e-token");
    window.localStorage.setItem("case_intel_username", "e2e");
  });
  await page.route("http://localhost:8000/api/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, "");
    const body = (data: unknown) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*" },
        body: JSON.stringify(data),
      });
    if (route.request().method() === "OPTIONS") return route.fulfill({ status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "*", "access-control-allow-methods": "*" } });
    if (path in overrides) return body(overrides[path]);
    if (path === `/cases/${CASE_ID}/`) return body(caseDetail);
    if (path === `/cases/${CASE_ID}/orders/`) return body(orders);
    if (path === "/hearings/") return body(hearings);
    if (path === "/documents/") return body(documents);
    if (path === "/case-events/") return body(events);
    if (path === "/advocate-profile/") return body({ advocate_name: "E2E", contact_email: "e2e@example.com", default_fee_amount: "0" });
    if (path === "/cases/refresh-all/") return body({ job_id: null });
    return body([]);
  });
}
