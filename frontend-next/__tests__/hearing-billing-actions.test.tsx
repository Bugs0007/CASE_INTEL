import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HearingBillingActions } from "@/components/hearings/hearing-billing-actions";
import type { AppearanceFee, Hearing, NestedAppearanceFee, SendInvoiceResult } from "@/types";

// The whole point of this suite: these calls must hit the REAL endpoints
// (appearanceFeesApi / travelBookingsApi), not a component-local mock
// standing in for missing UI. So the only thing mocked is the network
// layer itself -- everything above it (hooks, component) runs for real.
vi.mock("@/lib/api/billing", () => ({
  appearanceFeesApi: {
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    generateInvoice: vi.fn(),
    invoiceFile: vi.fn(),
    send: vi.fn(),
    markPaid: vi.fn(),
  },
  advocateProfileApi: {
    get: vi.fn(),
    update: vi.fn(),
  },
  travelBookingsApi: {
    list: vi.fn(),
    upload: vi.fn(),
    file: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
}));

import { appearanceFeesApi, travelBookingsApi } from "@/lib/api/billing";
import { showToast } from "@/components/ui/toaster";

const CASE_ID = 42;

function makeHearing(overrides: Partial<Hearing> = {}): Hearing {
  return {
    id: 7,
    case: CASE_ID,
    case_title: "Sharma vs. Meridian",
    hearing_date: "2026-09-01T05:00:00Z",
    hearing_type: "motion",
    hearing_type_display: "Motion",
    location: "District Court",
    judge: "Justice Rao",
    status: "scheduled",
    status_display: "Scheduled",
    notes: null,
    outcome: null,
    source: "manual",
    business_date: null,
    purpose: null,
    appearance_fee: null,
    travel_bookings: [],
    cause_list_status: "not_checked",
    cause_list_status_display: "Not checked",
    cause_list_item_number: "",
    cause_list_court_hall: "",
    cause_list_stage: "",
    cause_list_checked_at: null,
    order_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeFee(overrides: Partial<NestedAppearanceFee> = {}): NestedAppearanceFee {
  return {
    id: 99,
    amount: "15000.00",
    status: "pending",
    status_display: "Pending",
    invoice_number: "",
    invoiced_at: null,
    paid_at: null,
    sent_at: null,
    send_status: "not_sent",
    ...overrides,
  };
}

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("HearingBillingActions", () => {
  it("records a fee against the real appearanceFeesApi.create endpoint", async () => {
    const user = userEvent.setup();
    const created: AppearanceFee = {
      ...makeFee(),
      hearing: 7,
      case_id: CASE_ID,
      case_title: "Sharma vs. Meridian",
      hearing_date: "2026-09-01T05:00:00Z",
      invoice_sequence: null,
      sent_to_email: "",
      notes: "",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.mocked(appearanceFeesApi.create).mockResolvedValue(created);

    renderWithClient(<HearingBillingActions hearing={makeHearing()} caseId={CASE_ID} />);

    await user.type(screen.getByLabelText("Fee amount"), "15000");
    await user.click(screen.getByRole("button", { name: /record fee/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.create).toHaveBeenCalledWith({
        hearing: 7,
        amount: "15000",
      });
    });
    expect(showToast.success).toHaveBeenCalled();
  });

  it("generates an invoice for a pending fee via the real endpoint", async () => {
    const user = userEvent.setup();
    const fee = makeFee({ status: "pending" });
    const invoiced: AppearanceFee = {
      ...fee,
      status: "invoiced",
      invoice_number: "INV-0001",
      hearing: 7,
      case_id: CASE_ID,
      case_title: "Sharma vs. Meridian",
      hearing_date: "2026-09-01T05:00:00Z",
      invoice_sequence: 1,
      sent_to_email: "",
      notes: "",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.mocked(appearanceFeesApi.generateInvoice).mockResolvedValue(invoiced);

    renderWithClient(
      <HearingBillingActions hearing={makeHearing({ appearance_fee: fee })} caseId={CASE_ID} />,
    );

    await user.click(screen.getByRole("button", { name: /generate invoice/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.generateInvoice).toHaveBeenCalledWith(fee.id);
    });
    expect(showToast.success).toHaveBeenCalledWith(
      expect.stringContaining("INV-0001"),
      expect.any(String),
    );
  });

  it("sends the invoice and reports a real delivery distinctly from a logged one", async () => {
    const user = userEvent.setup();
    const fee = makeFee({ status: "invoiced", invoice_number: "INV-0001" });
    const result: SendInvoiceResult = {
      sent: true,
      recipient: "client@example.com",
      detail: "Invoice INV-0001 sent to client@example.com.",
      missing_env_vars: [],
      required_env_vars: [],
      fee: {
        ...fee,
        hearing: 7,
        case_id: CASE_ID,
        case_title: "Sharma vs. Meridian",
        hearing_date: "2026-09-01T05:00:00Z",
        invoice_sequence: 1,
        sent_to_email: "client@example.com",
        notes: "",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    };
    vi.mocked(appearanceFeesApi.send).mockResolvedValue(result);

    renderWithClient(
      <HearingBillingActions hearing={makeHearing({ appearance_fee: fee })} caseId={CASE_ID} />,
    );

    await user.click(screen.getByRole("button", { name: /send to billing contact/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.send).toHaveBeenCalledWith(fee.id);
    });
    expect(showToast.success).toHaveBeenCalledWith(
      "Invoice sent",
      expect.stringContaining("client@example.com"),
    );
    expect(showToast.warning).not.toHaveBeenCalled();
  });

  it("shows a distinct warning (not success) when the server only LOGGED the send", async () => {
    const user = userEvent.setup();
    const fee = makeFee({ status: "invoiced", invoice_number: "INV-0002" });
    const result: SendInvoiceResult = {
      sent: false,
      recipient: "client@example.com",
      detail: "Email is not configured on this server, so the invoice was logged instead of sent.",
      missing_env_vars: ["RESEND_API_KEY"],
      required_env_vars: ["RESEND_API_KEY", "DEFAULT_FROM_EMAIL"],
      fee: {
        ...fee,
        hearing: 7,
        case_id: CASE_ID,
        case_title: "Sharma vs. Meridian",
        hearing_date: "2026-09-01T05:00:00Z",
        invoice_sequence: 2,
        sent_to_email: "client@example.com",
        notes: "",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    };
    vi.mocked(appearanceFeesApi.send).mockResolvedValue(result);

    renderWithClient(
      <HearingBillingActions hearing={makeHearing({ appearance_fee: fee })} caseId={CASE_ID} />,
    );

    await user.click(screen.getByRole("button", { name: /send to billing contact/i }));

    await waitFor(() => {
      expect(showToast.warning).toHaveBeenCalledWith(
        "Invoice logged, not emailed",
        expect.stringContaining("RESEND_API_KEY"),
      );
    });
    expect(showToast.success).not.toHaveBeenCalled();
  });

  it("marks an invoiced fee paid via the real endpoint", async () => {
    const user = userEvent.setup();
    const fee = makeFee({ status: "invoiced", invoice_number: "INV-0003" });
    const paid: AppearanceFee = {
      ...fee,
      status: "paid",
      hearing: 7,
      case_id: CASE_ID,
      case_title: "Sharma vs. Meridian",
      hearing_date: "2026-09-01T05:00:00Z",
      invoice_sequence: 3,
      sent_to_email: "",
      notes: "",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    };
    vi.mocked(appearanceFeesApi.markPaid).mockResolvedValue(paid);

    renderWithClient(
      <HearingBillingActions hearing={makeHearing({ appearance_fee: fee })} caseId={CASE_ID} />,
    );

    await user.click(screen.getByRole("button", { name: /mark paid/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.markPaid).toHaveBeenCalledWith(fee.id);
    });
    expect(showToast.success).toHaveBeenCalledWith("Marked paid", expect.any(String));
  });

  it("surfaces the server's own error message on a failed mark-paid (e.g. 409)", async () => {
    const user = userEvent.setup();
    const fee = makeFee({ status: "invoiced" });
    const { APIError } = await import("@/lib/api/client");
    vi.mocked(appearanceFeesApi.markPaid).mockRejectedValue(
      new APIError(409, { detail: "This fee is already marked paid." }),
    );

    renderWithClient(
      <HearingBillingActions hearing={makeHearing({ appearance_fee: fee })} caseId={CASE_ID} />,
    );

    await user.click(screen.getByRole("button", { name: /mark paid/i }));

    await waitFor(() => {
      expect(showToast.error).toHaveBeenCalledWith(
        "Could not mark it paid",
        "This fee is already marked paid.",
      );
    });
  });

  it("uploads a travel booking file against the real travelBookingsApi.upload endpoint", async () => {
    const user = userEvent.setup();
    vi.mocked(travelBookingsApi.upload).mockResolvedValue({
      id: 5,
      booking_type: "travel",
      booking_type_display: "Travel",
      status: "booked",
      status_display: "Booked",
      filename: "ticket.pdf",
      created_at: "2026-01-01T00:00:00Z",
      hearing: 7,
      case_id: CASE_ID,
      file_type: "application/pdf",
      file_size: 1024,
      notes: "",
      updated_at: "2026-01-01T00:00:00Z",
    });

    renderWithClient(<HearingBillingActions hearing={makeHearing()} caseId={CASE_ID} />);

    const file = new File(["itinerary"], "ticket.pdf", { type: "application/pdf" });
    const input = screen.getByLabelText("Booking confirmation file");
    await user.upload(input, file);

    await waitFor(() => {
      expect(travelBookingsApi.upload).toHaveBeenCalledWith({
        file,
        hearing_id: 7,
        booking_type: "travel",
      });
    });
    expect(showToast.success).toHaveBeenCalledWith("Booking uploaded", expect.any(String));
  });
});
