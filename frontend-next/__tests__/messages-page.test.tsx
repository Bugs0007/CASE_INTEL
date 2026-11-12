import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ClientMessage, SendClientMessageResult, SentMessage } from "@/types";

const nav = vi.hoisted(() => ({ tab: "", replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/messages",
  useRouter: () => ({ push: vi.fn(), replace: nav.replace, back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.tab ? `tab=${nav.tab}` : ""),
}));

vi.mock("@/lib/api/clients", () => ({
  clientMessagesApi: { list: vi.fn(), update: vi.fn(), discard: vi.fn(), send: vi.fn() },
  sentMessagesApi: { list: vi.fn() },
  clientsApi: {},
  billingPortfolioApi: {},
  docTemplatesApi: {},
  refreshAllApi: {},
}));

vi.mock("@/lib/api/billing", () => ({
  advocateProfileApi: { get: vi.fn(), update: vi.fn() },
  appearanceFeesApi: {},
  travelBookingsApi: {},
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import MessagesPage from "@/app/(dashboard)/messages/page";
import { APIError } from "@/lib/api/client";
import { advocateProfileApi } from "@/lib/api/billing";
import { clientMessagesApi, sentMessagesApi } from "@/lib/api/clients";
import { showToast } from "@/components/ui/toaster";

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

function draft(over: Partial<ClientMessage> & { id: number }): ClientMessage {
  const contact = { contact_id: 9, name: "Meera Nair", email: "meera@example.com" };
  return {
    case: 3,
    case_title: "OS/10/2026 Meera Nair vs Reddy",
    case_number: "OS/10/2026",
    kind: "case_update",
    kind_display: "Case update",
    status: "draft",
    status_display: "Draft",
    subject: "Update on your matter",
    body: "Dear Meera Nair,\n\nThe matter was heard today and adjourned for counter.",
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
    created_at: daysAgo(2),
    updated_at: daysAgo(2),
    ...over,
  };
}

const DRAFTS = [
  draft({ id: 1 }),
  draft({
    id: 2,
    kind: "payment_reminder",
    kind_display: "Payment reminder",
    subject: "Reminder: invoice INV-0007",
    body: "Dear Rao,\n\nInvoice INV-0007 for Rs. 15,000 is still unpaid.",
    case_number: "WP/8841/2025",
    case_title: "Rao & Sons Builders vs GHMC",
    recipients: [{ contact_id: 4, name: "Rao & Sons", email: "rao@example.com" }],
    eligible_recipients: [{ contact_id: 4, name: "Rao & Sons", email: "rao@example.com" }],
    invoice_number: "INV-0007",
    created_at: daysAgo(5),
  }),
  draft({
    id: 3,
    subject: "Hearing update, no contact",
    case_number: "CC/312/2026",
    case_title: "Kavitha Reddy vs Ramesh Reddy",
    recipients: [],
    eligible_recipients: [],
  }),
];

function sentRow(over: Partial<SentMessage> & { id: number }): SentMessage {
  return {
    sent_at: daysAgo(1),
    sent_by: 1,
    sent_by_username: "advocate",
    kind: "case_update",
    kind_display: "Case update",
    delivery: "sent",
    delivery_display: "Sent",
    to_emails: ["meera@example.com"],
    cc_emails: [],
    subject: "Update on your matter",
    body_sha256: "x",
    case: 3,
    case_title: "Meera Nair vs Reddy",
    case_number: "OS/10/2026",
    message: null,
    fee: null,
    ...over,
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MessagesPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  nav.tab = "";
  vi.mocked(clientMessagesApi.list).mockResolvedValue(DRAFTS);
  vi.mocked(sentMessagesApi.list).mockResolvedValue([
    sentRow({ id: 1 }),
    sentRow({ id: 2, delivery: "logged", delivery_display: "Logged", subject: "Invoice INV-0003", kind: "invoice", kind_display: "Invoice", to_emails: ["rao@example.com"] }),
  ]);
  vi.mocked(advocateProfileApi.get).mockResolvedValue({ advocate_name: "Bhagath Kumar", contact_email: "e2e@example.com" } as never);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Messages: drafts", () => {
  it("shows each draft as a scannable row: kind, subject, who it is to, the case, the first words, how long ago", async () => {
    renderPage();
    const list = await screen.findByTestId("draft-list");
    const rows = within(list).getAllByRole("button", { expanded: false });
    expect(rows).toHaveLength(3);

    const update = rows[0];
    expect(within(update).getByText("Case update")).toBeInTheDocument();
    expect(within(update).getByText("Update on your matter")).toBeInTheDocument();
    // Who, which case, and what it says -- the "Dear Meera Nair," line is skipped.
    expect(within(update).getByText("To Meera Nair · OS/10/2026 Meera Nair vs Reddy")).toBeInTheDocument();
    expect(within(update).getByText("The matter was heard today and adjourned for counter.")).toBeInTheDocument();
    expect(within(update).getByText("2 days ago")).toBeInTheDocument();
    // Still a draft, so the marker says so.
    expect(within(update).getByText("Draft")).toBeInTheDocument();
    expect(within(update).queryByText("No email contact")).not.toBeInTheDocument();

    const reminder = rows[1];
    expect(within(reminder).getByText("Payment reminder")).toBeInTheDocument();
    expect(within(reminder).getByText(/^To Rao & Sons · WP\/8841\/2025/)).toBeInTheDocument();
    expect(within(reminder).getByText("Invoice INV-0007 for Rs. 15,000 is still unpaid.")).toBeInTheDocument();

    // A draft nobody can receive is flagged on the row, before it is opened.
    expect(within(rows[2]).getByText("No email contact")).toBeInTheDocument();
    expect(within(rows[2]).getByText(/^No recipient chosen/)).toBeInTheDocument();
  });

  it("counts each kind on its chip and narrows the list when one is pressed", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("draft-list");

    const chips = screen.getByRole("group", { name: "Filter drafts" });
    expect(within(chips).getByRole("button", { name: "All 3" })).toHaveAttribute("aria-pressed", "true");
    expect(within(chips).getByRole("button", { name: "Case updates 2" })).toBeInTheDocument();
    await user.click(within(chips).getByRole("button", { name: "Payment reminders 1" }));

    const list = screen.getByTestId("draft-list");
    expect(within(list).getAllByRole("button", { expanded: false })).toHaveLength(1);
    expect(within(list).getByText("Reminder: invoice INV-0007")).toBeInTheDocument();
    // The Drafts tab keeps the true total.
    expect(screen.getByRole("tab", { name: /Drafts \(3\)/ })).toBeInTheDocument();
  });

  it("searches by client, case or subject, and offers a way back when nothing matches", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("draft-list");

    await user.type(screen.getByLabelText("Search messages"), "kavitha");
    expect(within(screen.getByTestId("draft-list")).getAllByRole("button", { expanded: false })).toHaveLength(1);

    await user.clear(screen.getByLabelText("Search messages"));
    await user.type(screen.getByLabelText("Search messages"), "zzz");
    expect(screen.getByText(/Nothing matches your search here/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show everything" }));
    expect(await screen.findByTestId("draft-list")).toBeInTheDocument();
  });

  it("opens a draft in place and still sends it", async () => {
    const user = userEvent.setup();
    const result: SendClientMessageResult = {
      sent: true,
      recipients: ["meera@example.com"],
      detail: "Sent.",
      missing_env_vars: [],
      required_env_vars: [],
      message: draft({ id: 1, status: "sent" }),
    };
    vi.mocked(clientMessagesApi.send).mockResolvedValue(result);
    renderPage();
    const list = await screen.findByTestId("draft-list");

    await user.click(within(list).getAllByRole("button", { expanded: false })[0]);
    expect(screen.getByLabelText("Subject")).toHaveValue("Update on your matter");
    await waitFor(() => expect(screen.getByRole("button", { name: /^send$/i })).toBeEnabled());
    await user.click(screen.getByRole("button", { name: /^send$/i }));
    await waitFor(() => expect(clientMessagesApi.send).toHaveBeenCalledWith(1));
    await waitFor(() => expect(showToast.success).toHaveBeenCalledWith("Update sent", "Emailed to meera@example.com."));
  });

  it("explains an empty inbox, and an inbox that could not load", async () => {
    vi.mocked(clientMessagesApi.list).mockResolvedValueOnce([]);
    const first = renderPage();
    expect(await screen.findByText(/No drafts waiting/)).toBeInTheDocument();
    first.unmount();

    const user = userEvent.setup();
    vi.mocked(clientMessagesApi.list).mockRejectedValueOnce(new APIError(500, {}));
    renderPage();
    expect(await screen.findByText("Could not load drafts. Try again.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("draft-list")).toBeInTheDocument();
  });

  it("puts the sent log in the URL when its tab is pressed", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId("draft-list");
    await user.click(screen.getByRole("tab", { name: /Sent log/ }));
    expect(nav.replace).toHaveBeenCalledWith("/messages?tab=sent", { scroll: false });
  });
});

describe("Messages: sent log", () => {
  beforeEach(() => {
    nav.tab = "sent";
  });

  it("lists what went out, and separates what was emailed from what was only logged", async () => {
    const user = userEvent.setup();
    renderPage();
    const chips = await screen.findByRole("group", { name: "Filter sent messages" });
    expect(await within(chips).findByRole("button", { name: "All 2" })).toBeInTheDocument();
    expect(within(chips).getByRole("button", { name: "Emailed 1" })).toBeInTheDocument();
    expect(within(chips).getByRole("button", { name: "Logged, not emailed 1" })).toBeInTheDocument();

    await user.click(within(chips).getByRole("button", { name: "Logged, not emailed 1" }));
    const phoneList = screen.getByTestId("sent-log-list");
    expect(within(phoneList).getAllByRole("listitem")).toHaveLength(1);
    expect(within(phoneList).getByText("Invoice INV-0003")).toBeInTheDocument();
    expect(within(phoneList).getByText("Logged, not emailed")).toBeInTheDocument();
  });

  it("says so when nothing has been sent, and when the log could not load", async () => {
    vi.mocked(sentMessagesApi.list).mockResolvedValueOnce([]);
    const first = renderPage();
    expect(await screen.findByText("Nothing sent yet.")).toBeInTheDocument();
    first.unmount();

    vi.mocked(sentMessagesApi.list).mockRejectedValueOnce(new APIError(500, {}));
    renderPage();
    expect(await screen.findByText("Could not load the sent log. Try again.")).toBeInTheDocument();
  });
});
