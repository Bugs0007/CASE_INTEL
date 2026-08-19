import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HearingsList } from "@/components/hearings/hearings-list";
import type { AdvocateProfile, Hearing } from "@/types";

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
