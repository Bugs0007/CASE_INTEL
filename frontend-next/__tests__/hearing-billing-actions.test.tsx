import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HearingBillingActions } from "@/components/hearings/hearing-billing-actions";
import type {
  AdvocateProfile,
  AppearanceFee,
  FeeCategory,
  Hearing,
  NestedAppearanceFee,
  SendInvoiceResult,
} from "@/types";

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

import { advocateProfileApi, appearanceFeesApi, travelBookingsApi } from "@/lib/api/billing";
import { showToast } from "@/components/ui/toaster";

const CASE_ID = 42;

const CATEGORY_LABELS: Record<FeeCategory, string> = {
  appearance: "Appearance Fee",
  hotel: "Hotel",
  flight: "Flight",
  other: "Other",
};

function makeProfile(overrides: Partial<AdvocateProfile> = {}): AdvocateProfile {
  return {
    id: 1,
    letterhead_name: "",
    advocate_name: "",
    phone: "",
    reminder_after_days: 15,
    address: "",
    bar_registration_number: "",
    contact_email: "",
    default_fee_amount: "0.00",
    invoice_prefix: "INV",
    last_invoice_sequence: 0,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

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
    appearance_fees: [],
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
  const category = overrides.category ?? "appearance";
  return {
    id: 99,
    category,
    category_display: CATEGORY_LABELS[category],
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

/** The full API shape of a charge, as the mutation endpoints return it. */
function toFullFee(
  fee: NestedAppearanceFee,
  overrides: Partial<AppearanceFee> = {},
): AppearanceFee {
  return {
    ...fee,
    hearing: 7,
    case_id: CASE_ID,
    case_title: "Sharma vs. Meridian",
    hearing_date: "2026-09-01T05:00:00Z",
    invoice_sequence: null,
    sent_to_email: "",
    notes: "",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
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

function renderHearing(fees: NestedAppearanceFee[] = []) {
  return renderWithClient(
    <HearingBillingActions
      hearing={makeHearing({ appearance_fees: fees })}
      caseId={CASE_ID}
    />,
  );
}

/** The <li> for the charge with this category label. */
function rowFor(categoryLabel: string): HTMLElement {
  const rows = within(screen.getByRole("list", { name: "Charges" })).getAllByRole("listitem");
  const row = rows.find((r) => within(r).queryByText(categoryLabel));
  if (!row) throw new Error(`No charge row for "${categoryLabel}"`);
  return row;
}

beforeEach(() => {
  vi.clearAllMocks();
  // Default: a contact email is already set, so the gate this suite isn't
  // specifically testing stays out of the way. The tests that ARE about
  // the gate override this per-test.
  vi.mocked(advocateProfileApi.get).mockResolvedValue(
    makeProfile({ contact_email: "advocate@example.com" }),
  );
});

describe("HearingBillingActions: adding a charge", () => {
  it("offers the four categories and always shows the form, even once a charge exists", () => {
    renderHearing([makeFee()]);

    const select = screen.getByLabelText("Charge category");
    const options = within(select).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      "Appearance Fee",
      "Hotel",
      "Flight",
      "Other",
    ]);
    expect(select).toHaveValue("appearance");
    expect(screen.getByLabelText("Charge amount")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add charge/i })).toBeInTheDocument();
  });

  it("adds an appearance fee against the real appearanceFeesApi.create endpoint", async () => {
    const user = userEvent.setup();
    vi.mocked(appearanceFeesApi.create).mockResolvedValue(toFullFee(makeFee()));

    renderHearing();

    await user.type(screen.getByLabelText("Charge amount"), "15000");
    await user.click(screen.getByRole("button", { name: /add charge/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.create).toHaveBeenCalledWith({
        hearing: 7,
        category: "appearance",
        amount: "15000",
      });
    });
    expect(showToast.success).toHaveBeenCalledWith("Charge added", expect.any(String));
    // Cleared, ready for the next charge.
    expect(screen.getByLabelText("Charge amount")).toHaveValue("");
  });

  it("sends no amount for a blank appearance fee, so the server's default applies", async () => {
    const user = userEvent.setup();
    vi.mocked(appearanceFeesApi.create).mockResolvedValue(toFullFee(makeFee()));

    renderHearing();

    await user.click(screen.getByRole("button", { name: /add charge/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.create).toHaveBeenCalledWith({
        hearing: 7,
        category: "appearance",
      });
    });
    // Not "0" and not an empty string -- absent, so the fallback runs.
    expect(vi.mocked(appearanceFeesApi.create).mock.calls[0][0]).not.toHaveProperty("amount");
  });

  it("adds a hotel charge with the chosen category", async () => {
    const user = userEvent.setup();
    vi.mocked(appearanceFeesApi.create).mockResolvedValue(
      toFullFee(makeFee({ category: "hotel", amount: "4200.00" })),
    );

    renderHearing([makeFee()]);

    await user.selectOptions(screen.getByLabelText("Charge category"), "hotel");
    await user.type(screen.getByLabelText("Charge amount"), " 4200 ");
    await user.click(screen.getByRole("button", { name: /add charge/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.create).toHaveBeenCalledWith({
        hearing: 7,
        category: "hotel",
        // Trimmed.
        amount: "4200",
      });
    });
  });

  it.each(["hotel", "flight", "other"] as const)(
    "blocks a %s charge with no amount before it reaches the server",
    async (category) => {
      const user = userEvent.setup();
      renderHearing();

      await user.selectOptions(screen.getByLabelText("Charge category"), category);
      await user.click(screen.getByRole("button", { name: /add charge/i }));

      expect(appearanceFeesApi.create).not.toHaveBeenCalled();
      expect(showToast.error).toHaveBeenCalledWith("Enter an amount", expect.any(String));
      expect(showToast.success).not.toHaveBeenCalled();
    },
  );

  it("treats a whitespace-only amount as blank for a non-appearance charge", async () => {
    const user = userEvent.setup();
    renderHearing();

    await user.selectOptions(screen.getByLabelText("Charge category"), "flight");
    await user.type(screen.getByLabelText("Charge amount"), "   ");
    await user.click(screen.getByRole("button", { name: /add charge/i }));

    expect(appearanceFeesApi.create).not.toHaveBeenCalled();
    expect(showToast.error).toHaveBeenCalledWith("Enter an amount", expect.any(String));
  });

  it("only promises a default amount for an appearance fee, and only when one is set", async () => {
    const user = userEvent.setup();
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile({ default_fee_amount: "15000.00" }));
    renderHearing();

    const amount = screen.getByLabelText("Charge amount");
    await waitFor(() => expect(amount).toHaveAttribute("placeholder", expect.stringMatching(/^Amount \(default .*15,000\)$/)));

    await user.selectOptions(screen.getByLabelText("Charge category"), "hotel");
    expect(amount).toHaveAttribute("placeholder", "Amount");
  });

  it("promises no default when none is set (a blank would be a Rs. 0 charge)", () => {
    renderHearing();
    expect(screen.getByLabelText("Charge amount")).toHaveAttribute("placeholder", "Amount");
  });

  it("surfaces the server's field error when adding a charge is rejected", async () => {
    const user = userEvent.setup();
    const { APIError } = await import("@/lib/api/client");
    vi.mocked(appearanceFeesApi.create).mockRejectedValue(
      new APIError(400, { amount: ["A valid number is required."] }),
    );

    renderHearing();

    await user.type(screen.getByLabelText("Charge amount"), "4,200");
    await user.click(screen.getByRole("button", { name: /add charge/i }));

    await waitFor(() => {
      expect(showToast.error).toHaveBeenCalledWith(
        "Could not add the charge",
        "A valid number is required.",
      );
    });
    // A rejected charge keeps what was typed, so it can be corrected.
    expect(screen.getByLabelText("Charge amount")).toHaveValue("4,200");
  });
});

describe("HearingBillingActions: the charges on a hearing", () => {
  it("renders no list at all when there are no charges", () => {
    renderHearing();
    expect(screen.queryByRole("list", { name: "Charges" })).not.toBeInTheDocument();
  });

  it("renders one row per charge with its category, amount and status", () => {
    renderHearing([
      makeFee({ id: 1, category: "appearance", amount: "15000.00" }),
      makeFee({
        id: 2,
        category: "hotel",
        amount: "4250.50",
        status: "invoiced",
        status_display: "Invoiced",
        invoice_number: "INV-0002",
      }),
      makeFee({
        id: 3,
        category: "flight",
        amount: "6800.00",
        status: "paid",
        status_display: "Paid",
        invoice_number: "INV-0003",
      }),
    ]);

    expect(within(screen.getByRole("list", { name: "Charges" })).getAllByRole("listitem")).toHaveLength(3);

    const appearance = within(rowFor("Appearance Fee"));
    expect(appearance.getByText("₹15,000")).toBeInTheDocument();
    expect(appearance.getByText("Pending")).toBeInTheDocument();

    const hotel = within(rowFor("Hotel"));
    // Paise are shown, never rounded away on a bill.
    expect(hotel.getByText("₹4,250.50")).toBeInTheDocument();
    expect(hotel.getByText("Invoiced")).toBeInTheDocument();
    expect(hotel.getByText("INV-0002")).toBeInTheDocument();

    const flight = within(rowFor("Flight"));
    expect(flight.getByText("₹6,800")).toBeInTheDocument();
    expect(flight.getByText("Paid")).toBeInTheDocument();
  });

  it("gives each row only the actions its OWN status allows", () => {
    renderHearing([
      makeFee({ id: 1, category: "appearance", status: "pending" }),
      makeFee({
        id: 2,
        category: "hotel",
        status: "invoiced",
        status_display: "Invoiced",
        invoice_number: "INV-0002",
      }),
      makeFee({
        id: 3,
        category: "flight",
        status: "paid",
        status_display: "Paid",
        invoice_number: "INV-0003",
      }),
    ]);

    // Pending: can be invoiced, nothing else -- there is no PDF yet and
    // the server refuses to pay an un-invoiced fee.
    const pending = within(rowFor("Appearance Fee"));
    expect(pending.getByRole("button", { name: /generate invoice/i })).toBeInTheDocument();
    expect(pending.queryByRole("button", { name: /send to billing contact/i })).not.toBeInTheDocument();
    expect(pending.queryByRole("button", { name: /mark paid/i })).not.toBeInTheDocument();
    expect(pending.queryByRole("button", { name: /view pdf/i })).not.toBeInTheDocument();

    // Invoiced: send, pay, view -- but no second "generate".
    const invoiced = within(rowFor("Hotel"));
    expect(invoiced.getByRole("button", { name: /send to billing contact/i })).toBeInTheDocument();
    expect(invoiced.getByRole("button", { name: /mark paid/i })).toBeInTheDocument();
    expect(invoiced.getByRole("button", { name: /view pdf/i })).toBeInTheDocument();
    expect(invoiced.queryByRole("button", { name: /generate invoice/i })).not.toBeInTheDocument();

    // Paid: the receipt only.
    const paid = within(rowFor("Flight"));
    expect(paid.getByRole("button", { name: /view pdf/i })).toBeInTheDocument();
    expect(paid.queryByRole("button", { name: /generate invoice/i })).not.toBeInTheDocument();
    expect(paid.queryByRole("button", { name: /send to billing contact/i })).not.toBeInTheDocument();
    expect(paid.queryByRole("button", { name: /mark paid/i })).not.toBeInTheDocument();
  });

  it("names each row's buttons for their charge, so identical labels stay distinguishable", () => {
    renderHearing([
      makeFee({ id: 1, category: "hotel", status: "invoiced", status_display: "Invoiced", invoice_number: "INV-1" }),
      makeFee({ id: 2, category: "flight", status: "invoiced", status_display: "Invoiced", invoice_number: "INV-2" }),
    ]);

    expect(screen.getByRole("button", { name: "Mark Paid (Hotel)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark Paid (Flight)" })).toBeInTheDocument();
  });

  it("generates an invoice for the charge whose button was clicked, not the first one", async () => {
    const user = userEvent.setup();
    const appearance = makeFee({ id: 10, category: "appearance" });
    const hotel = makeFee({ id: 11, category: "hotel", amount: "4200.00" });
    vi.mocked(appearanceFeesApi.generateInvoice).mockResolvedValue(
      toFullFee({ ...hotel, status: "invoiced", invoice_number: "INV-0001" }, { invoice_sequence: 1 }),
    );

    renderHearing([appearance, hotel]);

    await user.click(within(rowFor("Hotel")).getByRole("button", { name: /generate invoice/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.generateInvoice).toHaveBeenCalledWith(hotel.id);
    });
    expect(appearanceFeesApi.generateInvoice).toHaveBeenCalledTimes(1);
    expect(showToast.success).toHaveBeenCalledWith(
      expect.stringContaining("INV-0001"),
      expect.any(String),
    );
  });

  it("keeps one row's in-flight request from disabling the other rows", async () => {
    const user = userEvent.setup();
    let finish!: (fee: AppearanceFee) => void;
    vi.mocked(appearanceFeesApi.generateInvoice).mockReturnValueOnce(
      new Promise<AppearanceFee>((resolve) => {
        finish = resolve;
      }),
    );
    const appearance = makeFee({ id: 10, category: "appearance" });
    const hotel = makeFee({ id: 11, category: "hotel" });

    renderHearing([appearance, hotel]);

    await user.click(within(rowFor("Appearance Fee")).getByRole("button", { name: /generate invoice/i }));

    // The clicked row is busy; the hotel row next to it is not.
    await waitFor(() => {
      expect(
        within(rowFor("Appearance Fee")).getByRole("button", { name: /generate invoice/i }),
      ).toBeDisabled();
    });
    expect(
      within(rowFor("Hotel")).getByRole("button", { name: /generate invoice/i }),
    ).toBeEnabled();

    finish(toFullFee({ ...appearance, status: "invoiced", invoice_number: "INV-0001" }));
    await waitFor(() => expect(showToast.success).toHaveBeenCalled());
  });

  it("sends the invoice and reports a real delivery distinctly from a logged one", async () => {
    const user = userEvent.setup();
    const fee = makeFee({ status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0001" });
    const result: SendInvoiceResult = {
      sent: true,
      recipient: "client@example.com",
      detail: "Invoice INV-0001 sent to client@example.com.",
      missing_env_vars: [],
      required_env_vars: [],
      fee: toFullFee(fee, { invoice_sequence: 1, sent_to_email: "client@example.com" }),
    };
    vi.mocked(appearanceFeesApi.send).mockResolvedValue(result);

    renderHearing([fee]);

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
    const fee = makeFee({ status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0002" });
    const result: SendInvoiceResult = {
      sent: false,
      recipient: "client@example.com",
      detail: "Email is not configured on this server, so the invoice was logged instead of sent.",
      missing_env_vars: ["RESEND_API_KEY"],
      required_env_vars: ["RESEND_API_KEY", "DEFAULT_FROM_EMAIL"],
      fee: toFullFee(fee, { invoice_sequence: 2, sent_to_email: "client@example.com" }),
    };
    vi.mocked(appearanceFeesApi.send).mockResolvedValue(result);

    renderHearing([fee]);

    await user.click(screen.getByRole("button", { name: /send to billing contact/i }));

    await waitFor(() => {
      expect(showToast.warning).toHaveBeenCalledWith(
        "Invoice logged, not emailed",
        expect.stringContaining("RESEND_API_KEY"),
      );
    });
    expect(showToast.success).not.toHaveBeenCalled();
  });

  it("marks the clicked charge paid via the real endpoint", async () => {
    const user = userEvent.setup();
    const hotel = makeFee({ id: 21, category: "hotel", status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0003" });
    const flight = makeFee({ id: 22, category: "flight", status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0004" });
    vi.mocked(appearanceFeesApi.markPaid).mockResolvedValue(
      toFullFee({ ...flight, status: "paid" }, { invoice_sequence: 4 }),
    );

    renderHearing([hotel, flight]);

    await user.click(within(rowFor("Flight")).getByRole("button", { name: /mark paid/i }));

    await waitFor(() => {
      expect(appearanceFeesApi.markPaid).toHaveBeenCalledWith(flight.id);
    });
    expect(appearanceFeesApi.markPaid).toHaveBeenCalledTimes(1);
    expect(showToast.success).toHaveBeenCalledWith("Marked paid", expect.any(String));
  });

  it("surfaces the server's own error message on a failed mark-paid (e.g. 409)", async () => {
    const user = userEvent.setup();
    const fee = makeFee({ status: "invoiced", status_display: "Invoiced" });
    const { APIError } = await import("@/lib/api/client");
    vi.mocked(appearanceFeesApi.markPaid).mockRejectedValue(
      new APIError(409, { detail: "This fee is already marked paid." }),
    );

    renderHearing([fee]);

    await user.click(screen.getByRole("button", { name: /mark paid/i }));

    await waitFor(() => {
      expect(showToast.error).toHaveBeenCalledWith(
        "Could not mark it paid",
        "This fee is already marked paid.",
      );
    });
  });
});

describe("HearingBillingActions: the contact-email gate", () => {
  it("shows guidance instead of the Send button when the advocate has no contact email set", async () => {
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile({ contact_email: "" }));
    const fee = makeFee({ status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0004" });

    renderHearing([fee]);

    await waitFor(() => {
      expect(screen.getByText(/no contact email set/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: /send to billing contact/i })).not.toBeInTheDocument();
    const settingsLink = screen.getByRole("link", { name: /add it in settings/i });
    expect(settingsLink).toHaveAttribute("href", "/settings");
    // Mark Paid is unrelated to the contact-email gate and must still work.
    expect(screen.getByRole("button", { name: /mark paid/i })).toBeInTheDocument();
    expect(appearanceFeesApi.send).not.toHaveBeenCalled();
  });

  it("warns once for the whole block, however many invoiced charges there are", async () => {
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile({ contact_email: "" }));

    renderHearing([
      makeFee({ id: 1, category: "appearance", status: "invoiced", status_display: "Invoiced", invoice_number: "INV-1" }),
      makeFee({ id: 2, category: "hotel", status: "invoiced", status_display: "Invoiced", invoice_number: "INV-2" }),
    ]);

    await waitFor(() => {
      expect(screen.getAllByText(/no contact email set/i)).toHaveLength(1);
    });
    expect(screen.queryAllByRole("button", { name: /send to billing contact/i })).toHaveLength(0);
    expect(screen.getAllByRole("button", { name: /mark paid/i })).toHaveLength(2);
  });

  it("does not warn when nothing is invoiced yet, since there is nothing to send", async () => {
    vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile({ contact_email: "" }));

    renderHearing([makeFee({ status: "pending" })]);

    // Let the profile load, so this isn't passing merely because it was
    // still undefined.
    await waitFor(() => expect(advocateProfileApi.get).toHaveBeenCalled());
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /generate invoice/i })).toBeInTheDocument();
    });
    expect(screen.queryByText(/no contact email set/i)).not.toBeInTheDocument();
  });

  it("shows the normal Send button once the advocate has a contact email set", async () => {
    vi.mocked(advocateProfileApi.get).mockResolvedValue(
      makeProfile({ contact_email: "advocate@example.com" }),
    );
    const fee = makeFee({ status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0005" });

    renderHearing([fee]);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /send to billing contact/i })).toBeInTheDocument();
    });
    expect(screen.queryByText(/no contact email set/i)).not.toBeInTheDocument();
  });
});

describe("HearingBillingActions: travel bookings", () => {
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

    renderHearing();

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

  it("keeps the booking-type picker separate from the charge-category picker", () => {
    renderHearing([makeFee()]);

    // Two different selects for two different things: what a charge is
    // billed as, and what kind of confirmation document is being uploaded.
    const booking = screen.getByLabelText("Booking type");
    const charge = screen.getByLabelText("Charge category");
    expect(booking).not.toBe(charge);
    expect(within(booking).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Travel",
      "Hotel",
      "Other",
    ]);
  });
});
