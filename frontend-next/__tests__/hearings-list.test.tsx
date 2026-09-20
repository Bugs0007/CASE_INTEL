import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HearingsList } from "@/components/hearings/hearings-list";
import type { AdvocateProfile, Hearing, NestedAppearanceFee } from "@/types";

// HearingItem renders HearingBillingActions, which calls useAdvocateProfile()
// -- mock the network layer the same way hearing-billing-actions.test.tsx
// does, so this suite stays focused on what HearingsList itself renders.
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

import { advocateProfileApi } from "@/lib/api/billing";

const CASE_ID = 42;

function makeProfile(overrides: Partial<AdvocateProfile> = {}): AdvocateProfile {
  return {
    id: 1,
    letterhead_name: "",
    address: "",
    bar_registration_number: "",
    contact_email: "advocate@example.com",
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
    source: "ecourts",
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
  return {
    id: 1,
    category: "appearance",
    category_display: "Appearance Fee",
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
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.mocked(advocateProfileApi.get).mockResolvedValue(makeProfile());
});

describe("HearingsList", () => {
  it("shows the eCourts purpose of hearing directly on the card", () => {
    const hearing = makeHearing({ purpose: "CALL WITH IAS" });

    renderWithClient(<HearingsList caseId={CASE_ID} hearings={[hearing]} />);

    expect(screen.getByText("CALL WITH IAS")).toBeInTheDocument();
  });

  it("renders nothing extra when purpose is unset (e.g. a manual hearing)", () => {
    const hearing = makeHearing({ purpose: null, source: "manual" });

    renderWithClient(<HearingsList caseId={CASE_ID} hearings={[hearing]} />);

    // Judge still renders (unrelated field) -- purpose specifically must not.
    expect(screen.getByText("Justice Rao")).toBeInTheDocument();
    expect(screen.queryByText("CALL WITH IAS")).not.toBeInTheDocument();
  });
});

describe("HearingsList charge badges", () => {
  // The badge is one text run -- "Hotel · ₹4,200 · Pending" -- while the
  // billing rows underneath render category, amount and status as separate
  // elements, so matching the whole run finds the badge and only the badge.

  it("renders one badge per charge, each prefixed with its category", () => {
    const hearing = makeHearing({
      appearance_fees: [
        makeFee({ id: 1, category: "appearance", category_display: "Appearance Fee", amount: "15000.00" }),
        makeFee({ id: 2, category: "hotel", category_display: "Hotel", amount: "4200.00" }),
        makeFee({
          id: 3,
          category: "flight",
          category_display: "Flight",
          amount: "6800.00",
          status: "paid",
          status_display: "Paid",
          invoice_number: "INV-0003",
        }),
      ],
    });

    renderWithClient(<HearingsList caseId={CASE_ID} hearings={[hearing]} />);

    expect(screen.getByText(/^Appearance Fee · .*15,000 · Pending$/)).toBeInTheDocument();
    expect(screen.getByText(/^Hotel · .*4,200 · Pending$/)).toBeInTheDocument();
    expect(screen.getByText(/^Flight · .*6,800 · Paid$/)).toBeInTheDocument();
  });

  it("marks only a paid charge as settled, leaving the others pending", () => {
    const hearing = makeHearing({
      appearance_fees: [
        makeFee({ id: 1, category: "hotel", category_display: "Hotel", status: "invoiced", status_display: "Invoiced", invoice_number: "INV-0002" }),
        makeFee({ id: 2, category: "flight", category_display: "Flight", status: "paid", status_display: "Paid", invoice_number: "INV-0003" }),
      ],
    });

    renderWithClient(<HearingsList caseId={CASE_ID} hearings={[hearing]} />);

    // "invoiced" is billed-but-unpaid, the same bucket as not-yet-billed.
    expect(screen.getByText(/^Hotel · /)).toHaveClass("ci-chip--pending");
    expect(screen.getByText(/^Flight · /)).toHaveClass("ci-chip--ok");
  });

  it("explains the charge's state in a tooltip, naming its category", () => {
    const hearing = makeHearing({
      appearance_fees: [
        makeFee({
          id: 2,
          category: "hotel",
          category_display: "Hotel",
          status: "invoiced",
          status_display: "Invoiced",
          invoice_number: "INV-0002",
          send_status: "logged",
        }),
      ],
    });

    renderWithClient(<HearingsList caseId={CASE_ID} hearings={[hearing]} />);

    // "logged" must never read as delivered.
    expect(screen.getByText(/^Hotel · /)).toHaveAttribute(
      "title",
      "Hotel: Invoiced as INV-0002, logged only (email not configured on the server)",
    );
  });

  it("does not round away paise on a charge amount", () => {
    const hearing = makeHearing({
      appearance_fees: [
        makeFee({ id: 2, category: "hotel", category_display: "Hotel", amount: "4250.50" }),
      ],
    });

    renderWithClient(<HearingsList caseId={CASE_ID} hearings={[hearing]} />);

    expect(screen.getByText(/^Hotel · .*4,250\.50 · Pending$/)).toBeInTheDocument();
  });

  it("renders no charge badges for a hearing with no charges", () => {
    renderWithClient(<HearingsList caseId={CASE_ID} hearings={[makeHearing()]} />);

    expect(screen.queryByText(/ · Pending$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/ · Paid$/)).not.toBeInTheDocument();
  });
});
