import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { AppearanceFee } from "@/types";

// Only the network layer is mocked: the hooks, the model and every component
// run for real, so a click really goes through useMarkFeesPaid and the cache.
vi.mock("next/navigation", () => ({
  usePathname: () => "/billing",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api/billing", () => ({
  appearanceFeesApi: {
    list: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    generateInvoice: vi.fn(),
    invoiceFile: vi.fn(),
    send: vi.fn(),
    markPaid: vi.fn(),
  },
  advocateProfileApi: { get: vi.fn(), update: vi.fn() },
  travelBookingsApi: {},
}));

vi.mock("@/lib/api/cases", () => ({
  casesApi: { list: vi.fn(), get: vi.fn(), update: vi.fn() },
}));

vi.mock("@/lib/api/clients", () => ({
  billingPortfolioApi: { get: vi.fn() },
  clientsApi: { list: vi.fn(), statementPdf: vi.fn() },
  clientMessagesApi: {},
  sentMessagesApi: {},
  docTemplatesApi: {},
  refreshAllApi: {},
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import BillingPage from "@/app/(dashboard)/billing/page";
import { APIError } from "@/lib/api/client";
import { advocateProfileApi, appearanceFeesApi } from "@/lib/api/billing";
import { casesApi } from "@/lib/api/cases";
import { billingPortfolioApi, clientsApi } from "@/lib/api/clients";
import { showToast } from "@/components/ui/toaster";

const NOW = () => new Date().toISOString();
const ago = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();

function makeFee(over: Partial<AppearanceFee> & { id: number }): AppearanceFee {
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

function seedFees(): AppearanceFee[] {
  return [
    makeFee({ id: 1, case_id: 11, status: "invoiced", invoice_number: "INV-0007", invoiced_at: ago(12), amount: "15000.00" }),
    makeFee({ id: 2, case_id: 11, status: "pending", amount: "3000.00" }),
    makeFee({ id: 3, case_id: 12, status: "invoiced", invoice_number: "INV-0003", invoiced_at: ago(41), amount: "8000.00" }),
    makeFee({ id: 4, case_id: 12, status: "invoiced", invoice_number: "INV-0005", invoiced_at: ago(5), amount: "4000.00" }),
    makeFee({ id: 5, case_id: 11, status: "paid", invoice_number: "INV-0001", invoiced_at: ago(40), paid_at: NOW(), amount: "6000.00" }),
    makeFee({ id: 6, case_id: 13, status: "pending", amount: "2500.00" }),
  ];
}

const CASES = [
  { id: 11, case_number: "CC/312/2026", title: "Meera Nair vs. Sundaram Finance Ltd", client: 101, client_detail: { id: 101, name: "Meera Nair", client_type: "individual" } },
  { id: 12, case_number: "WP/8841/2025", title: "Rao & Sons Builders vs. GHMC", client: 102, client_detail: { id: 102, name: "Rao & Sons Builders", client_type: "business" } },
  { id: 13, case_number: "WP/1/2026", title: "Anand Textiles vs. Union of India", client: null, client_detail: null },
];

let serverFees: AppearanceFee[] = [];

function wire() {
  serverFees = seedFees();
  vi.mocked(appearanceFeesApi.list).mockImplementation(async () => serverFees.map((f) => ({ ...f })));
  vi.mocked(appearanceFeesApi.markPaid).mockImplementation(async (id: number) => {
    const fee = serverFees.find((f) => f.id === id)!;
    Object.assign(fee, { status: "paid", status_display: "Paid", paid_at: NOW() });
    return { ...fee };
  });
  vi.mocked(appearanceFeesApi.generateInvoice).mockImplementation(async (id: number) => {
    const fee = serverFees.find((f) => f.id === id)!;
    Object.assign(fee, { status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0009", invoiced_at: NOW() });
    return { ...fee };
  });
  vi.mocked(casesApi.list).mockResolvedValue(CASES as never);
  vi.mocked(casesApi.update).mockResolvedValue({ ...CASES[2], client: 101 } as never);
  vi.mocked(advocateProfileApi.get).mockResolvedValue({ default_fee_amount: "5000.00", contact_email: "a@example.com" } as never);
  vi.mocked(clientsApi.list).mockResolvedValue([{ id: 101, name: "Meera Nair" }] as never);
  vi.mocked(billingPortfolioApi.get).mockResolvedValue({
    uninvoiced_hearings: [],
    uninvoiced_hearings_total: 0,
  } as never);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <BillingPage />
    </QueryClientProvider>,
  );
}

const groupTitles = () => screen.getAllByTestId("fee-group").map((g) => g.getAttribute("aria-label"));

beforeEach(() => {
  vi.clearAllMocks();
  wire();
});
afterEach(() => {
  delete (Element.prototype as Partial<Element>).scrollIntoView;
  vi.unstubAllGlobals();
  document.getElementById("mobile-subbar-slot")?.remove();
});

describe("Billing page", () => {
  it("totals what is owed on tiles and lists the charges by client, longest-unpaid first", async () => {
    renderPage();
    await screen.findAllByTestId("fee-group");

    const tile = (name: RegExp) => screen.getByRole("button", { name });
    expect(tile(/^Outstanding/)).toHaveTextContent("₹32,500");
    expect(tile(/^Outstanding/)).toHaveTextContent("5 charges unpaid");
    expect(tile(/^To invoice/)).toHaveTextContent("₹5,500");
    expect(tile(/^Awaiting payment/)).toHaveTextContent("₹27,000");
    expect(tile(/^Awaiting payment/)).toHaveTextContent("1 overdue · oldest 41 d");
    expect(tile(/^Paid this month/)).toHaveTextContent("₹6,000");
    expect(tile(/^Outstanding/)).toHaveAttribute("aria-pressed", "true");

    // Rao's 41-day-old invoice puts him first; the case with no client is last.
    expect(groupTitles()).toEqual(["Rao & Sons Builders", "Meera Nair", "WP/1/2026"]);
    expect(screen.getByRole("heading", { name: "Outstanding by client" })).toBeInTheDocument();
    expect(screen.getByText("41 days unpaid")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Statement for Meera Nair" })).toBeInTheDocument();
  });

  it("offers each charge only the step the server allows", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    // Invoiced: Mark paid. Pending: Generate invoice, and no Mark paid.
    expect(screen.getByRole("button", { name: "Mark INV-0007 paid" })).toBeInTheDocument();
    const pending = screen.getAllByTestId("fee-row").filter((r) => r.dataset.status === "pending");
    expect(pending).toHaveLength(2);
    for (const row of pending) {
      expect(within(row).getByRole("button", { name: /^Generate invoice for / })).toBeInTheDocument();
      expect(within(row).queryByRole("button", { name: /paid/i })).not.toBeInTheDocument();
    }

    // Paid: the date and the PDF, and nothing to press twice.
    await user.click(screen.getByRole("button", { name: /^Paid this month/ }));
    const paidRows = await screen.findAllByTestId("fee-row");
    expect(paidRows).toHaveLength(1);
    expect(within(paidRows[0]).queryByRole("button", { name: /Mark|Generate/ })).not.toBeInTheDocument();
    expect(within(paidRows[0]).getByRole("button", { name: "View PDF INV-0001" })).toBeInTheDocument();
    expect(paidRows[0]).toHaveTextContent(/paid \d+ \w{3}/);
  });

  it("confirms with client, case, invoice and amount before marking paid, then shows it paid", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    await user.click(screen.getByRole("button", { name: "Mark INV-0007 paid" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as paid" });
    expect(within(dialog).getByText("Meera Nair")).toBeInTheDocument();
    expect(within(dialog).getByText(/CC\/312\/2026/)).toBeInTheDocument();
    expect(within(dialog).getByText("INV-0007")).toBeInTheDocument();
    expect(within(dialog).getAllByText("₹15,000").length).toBeGreaterThan(0);
    expect(within(dialog).getByText(/can't be undone/)).toBeInTheDocument();
    // Nothing has happened yet.
    expect(appearanceFeesApi.markPaid).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Mark paid · ₹15,000" }));
    await waitFor(() => expect(appearanceFeesApi.markPaid).toHaveBeenCalledTimes(1));
    expect(appearanceFeesApi.markPaid).toHaveBeenCalledWith(1);
    await waitFor(() =>
      expect(showToast.success).toHaveBeenCalledWith("Marked paid", "INV-0007 · ₹15,000 is settled."),
    );

    // The sheet leaves, the row is out of the unpaid list, the tiles moved.
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Mark as paid" })).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Mark INV-0007 paid" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Outstanding/ })).toHaveTextContent("₹17,500");
    expect(screen.getByRole("button", { name: /^Paid this month/ })).toHaveTextContent("₹21,000");

    await user.click(screen.getByRole("button", { name: /^Paid this month/ }));
    const rows = await screen.findAllByTestId("fee-row");
    expect(rows.map((r) => r.dataset.status)).toEqual(["paid", "paid"]);
  });

  it("does not mark anything paid when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    await user.click(screen.getByRole("button", { name: "Mark INV-0007 paid" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as paid" });
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Mark as paid" })).not.toBeInTheDocument());
    expect(appearanceFeesApi.markPaid).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Mark INV-0007 paid" })).toBeInTheDocument();
  });

  it("keeps the confirmation open and shows the server's reason when it refuses", async () => {
    const user = userEvent.setup();
    vi.mocked(appearanceFeesApi.markPaid).mockRejectedValueOnce(
      new APIError(409, { detail: "This fee is already marked paid." }),
    );
    renderPage();
    await screen.findAllByTestId("fee-group");

    await user.click(screen.getByRole("button", { name: "Mark INV-0007 paid" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark as paid" });
    await user.click(within(dialog).getByRole("button", { name: "Mark paid · ₹15,000" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("This fee is already marked paid.");
    expect(showToast.error).toHaveBeenCalledWith("Could not mark it paid", "This fee is already marked paid.");
    expect(showToast.success).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Mark as paid" })).toBeInTheDocument();
    expect(appearanceFeesApi.markPaid).toHaveBeenCalledTimes(1);
  });

  it("marks all of a client's invoices paid after one confirmation that lists them and their total", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    // Only a client with two or more invoiced charges gets the button.
    expect(screen.getAllByRole("button", { name: /^Mark all \d+ paid$/ })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Mark all 2 paid" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark invoices as paid" });
    const list = within(dialog).getByRole("list", { name: "Invoices to mark paid" });
    expect(within(list).getByText("INV-0003")).toBeInTheDocument();
    expect(within(list).getByText("INV-0005")).toBeInTheDocument();
    expect(within(dialog).getByText("Total")).toBeInTheDocument();
    expect(appearanceFeesApi.markPaid).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole("button", { name: "Mark 2 paid · ₹12,000" }));
    await waitFor(() => expect(appearanceFeesApi.markPaid).toHaveBeenCalledTimes(2));
    expect(vi.mocked(appearanceFeesApi.markPaid).mock.calls.map((c) => c[0])).toEqual([3, 4]);
    await waitFor(() =>
      expect(showToast.success).toHaveBeenCalledWith("Marked 2 paid", "₹12,000 from Rao & Sons Builders is settled."),
    );
    await waitFor(() => expect(groupTitles()).toEqual(["Meera Nair", "WP/1/2026"]));
  });

  it("says so when only some of a batch went through", async () => {
    const user = userEvent.setup();
    vi.mocked(appearanceFeesApi.markPaid)
      .mockImplementationOnce(async (id: number) => {
        const fee = serverFees.find((f) => f.id === id)!;
        Object.assign(fee, { status: "paid", paid_at: NOW() });
        return { ...fee };
      })
      .mockRejectedValueOnce(new APIError(409, { detail: "This fee is already marked paid." }));
    renderPage();
    await screen.findAllByTestId("fee-group");

    await user.click(screen.getByRole("button", { name: "Mark all 2 paid" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark invoices as paid" });
    await user.click(within(dialog).getByRole("button", { name: /^Mark 2 paid/ }));

    await waitFor(() =>
      expect(showToast.warning).toHaveBeenCalledWith("Marked 1 of 2 paid", "This fee is already marked paid."),
    );
    expect(showToast.success).not.toHaveBeenCalled();
  });

  it("generates the invoice inline, and the charge then offers Mark paid", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    await user.click(screen.getByRole("button", { name: "Generate invoice for CC/312/2026, Appearance Fee" }));
    await waitFor(() => expect(appearanceFeesApi.generateInvoice).toHaveBeenCalledWith(2));
    await waitFor(() =>
      expect(showToast.success).toHaveBeenCalledWith(
        "Invoice INV-0009 generated",
        expect.stringContaining("PDF"),
      ),
    );
    expect(await screen.findByRole("button", { name: "Mark INV-0009 paid" })).toBeInTheDocument();
  });

  it("assigns a case with no client to one", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    await user.selectOptions(screen.getByLabelText("Assign WP/1/2026 to a client"), "101");
    await waitFor(() => expect(casesApi.update).toHaveBeenCalledWith(13, { client: 101 }));
    await waitFor(() => expect(showToast.success).toHaveBeenCalledWith("Client assigned"));
  });

  it("searches by client, case or invoice number, and says when nothing matches", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    await user.type(screen.getByLabelText("Search charges"), "rao");
    expect(groupTitles()).toEqual(["Rao & Sons Builders"]);

    await user.clear(screen.getByLabelText("Search charges"));
    await user.type(screen.getByLabelText("Search charges"), "INV-0007");
    expect(groupTitles()).toEqual(["Meera Nair"]);

    await user.clear(screen.getByLabelText("Search charges"));
    await user.type(screen.getByLabelText("Search charges"), "zzz");
    expect(screen.getByText(/No charges match/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(groupTitles()).toHaveLength(3);
  });

  it("says nothing is waiting when every charge is settled, and when none exist", async () => {
    serverFees = serverFees.map((f) => ({ ...f, status: "paid" as const, paid_at: NOW() }));
    const first = renderPage();
    expect(await screen.findByText(/Nothing is waiting on you/)).toBeInTheDocument();
    first.unmount();

    serverFees = [];
    renderPage();
    expect(await screen.findByText(/No charges recorded yet/)).toBeInTheDocument();
  });

  it("shows a loading state, then an error with a way to retry", async () => {
    const user = userEvent.setup();
    vi.mocked(appearanceFeesApi.list).mockRejectedValueOnce(new APIError(500, {}));
    renderPage();
    expect(screen.getByLabelText("Loading billing")).toBeInTheDocument();
    expect(await screen.findByText("Could not load billing. Try refreshing the page.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findAllByTestId("fee-group")).toHaveLength(3);
  });

  it("keeps the aging card in step with the list", async () => {
    renderPage();
    await screen.findAllByTestId("fee-group");
    const aging = screen.getByTestId("aging-buckets");
    expect(within(aging).getByText("31-60 days").parentElement).toHaveTextContent("₹8,000");
    expect(within(aging).getByText("0-30 days").parentElement).toHaveTextContent("₹19,000");
  });
});

describe("Billing page on a phone", () => {
  it("shows the headline card and pins the filter tabs, which switch the list", async () => {
    const slot = document.createElement("div");
    slot.id = "mobile-subbar-slot";
    document.body.appendChild(slot);
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: true,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }));
    // jsdom has no scrollIntoView; a tab pressed while scrolled brings the list's top back.
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const user = userEvent.setup();
    renderPage();
    await screen.findAllByTestId("fee-group");

    expect(screen.getByTestId("billing-hero")).toHaveTextContent("₹32,500");
    // The desktop tiles are not in the page at all.
    expect(screen.queryByRole("button", { name: /^Outstanding/ })).not.toBeInTheDocument();

    const tabs = await within(slot).findByRole("tablist", { name: "Show charges" });
    expect(within(tabs).getByRole("tab", { name: /^Unpaid/ })).toHaveAttribute("aria-selected", "true");
    await user.click(within(tabs).getByRole("tab", { name: /^To invoice/ }));
    expect(screen.getByRole("heading", { name: "To invoice, by client" })).toBeInTheDocument();
    expect(screen.getAllByTestId("fee-row").every((r) => r.dataset.status === "pending")).toBe(true);
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
  });
});
