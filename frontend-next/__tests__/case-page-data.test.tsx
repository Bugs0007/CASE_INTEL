import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CourtTrackingCard } from "@/components/cases/court-tracking-card";
import { OrderOverviewCard } from "@/components/cases/order-overview";
import { CaseOverview } from "@/components/cases/case-overview";
import type { Case, CourtOrder, Hearing } from "@/types";

vi.mock("@/lib/api/case-tracking", () => ({
  caseTrackingApi: { refresh: vi.fn(), untrack: vi.fn(), preview: vi.fn(), confirm: vi.fn(), courtStructure: vi.fn() },
}));

function wrap(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
const dateKey = (offsetDays: number) => new Date(Date.now() + offsetDays * 86_400_000).toISOString().slice(0, 10);

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: 28,
    case_number: "WP/26147/2026",
    title: "S.Sashi Kumar vs The State of Telangana",
    client_name: "",
    client: null,
    client_detail: null,
    client_contacts: [],
    opposing_party: null,
    user_party_role: "unknown",
    case_type: null,
    status: "open",
    priority: "medium",
    filing_date: null,
    notes: null,
    created_at: daysAgo(40),
    document_count: 0,
    hearing_count: 0,
    thread_count: 0,
    conversation_count: 0,
    cnr_number: "HBHC010536082026",
    court_type: "high_court",
    tracking_config: null,
    tracking_enabled: true,
    fetch_status: "success",
    last_fetched_at: daysAgo(31),
    needs_attention: false,
    next_hearing_date: null,
    fee_summary: {} as Case["fee_summary"],
    tracking_snapshot: {
      case_status: "Pending", case_stage: "FOR ADMISSION", court_and_judge: "APARESH KUMAR SINGH",
      court_name: "", nature_of_disposal: "", next_hearing_date: null,
    },
    tracking_freshness: {
      stale: true, reasons: ["last_checked"], stale_after_days: 3, awaiting_update_count: 0, refresh_available_at: null,
    },
    disposal: null,
    parties: { petitioner: "S.Sashi Kumar", respondent: "The State of Telangana", source: "record", ours: "", opposing: "" },
    ...overrides,
  };
}

function hearing(date: string, overrides: Partial<Hearing> = {}): Hearing {
  return {
    id: Math.floor(Math.random() * 1e6), case: 28, case_title: "", hearing_date: `${date}T00:00:00Z`,
    hearing_type: "other", hearing_type_display: "Other", location: "", judge: "", status: "completed",
    status_display: "Completed", notes: null, outcome: null, source: "ecourts", business_date: null, purpose: "",
    appearance_fees: [], travel_bookings: [], cause_list_status: "not_checked", cause_list_status_display: "",
    cause_list_item_number: "", cause_list_court_hall: "", cause_list_stage: "", cause_list_checked_at: null,
    order_summary: null, created_at: "", updated_at: "", ...overrides,
  } as Hearing;
}

describe("Court Tracking on stale data", () => {
  it("says Outdated and never 'None scheduled'", () => {
    // Case 28 in production: refreshed a month ago, Status "—", Next
    // Hearing "None scheduled" -- until a refresh filled it all in.
    wrap(<CourtTrackingCard caseItem={makeCase()} hearings={[hearing(dateKey(-40))]} />);

    expect(screen.getByText("Outdated")).toBeInTheDocument();
    expect(screen.getByText("Unknown -- refresh to check")).toBeInTheDocument();
    expect(screen.queryByText("None scheduled")).not.toBeInTheDocument();
    // What eCourts last said, instead of dashes.
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("APARESH KUMAR SINGH")).toBeInTheDocument();
    expect(screen.getByText("FOR ADMISSION")).toBeInTheDocument();
  });

  it("counts past hearings still marked scheduled", () => {
    const caseItem = makeCase({
      last_fetched_at: daysAgo(1),
      tracking_freshness: {
        stale: true, reasons: ["past_hearing_unconfirmed"], stale_after_days: 3, awaiting_update_count: 1,
        refresh_available_at: null,
      },
    });
    wrap(<CourtTrackingCard caseItem={caseItem} hearings={[hearing(dateKey(-1), { status: "scheduled" })]} />);
    expect(screen.getByText(/1 past hearing awaiting an update/)).toBeInTheDocument();
  });

  it("explains a disabled Refresh instead of just greying it out", () => {
    const caseItem = makeCase({
      last_fetched_at: new Date(Date.now() - 7 * 60_000).toISOString(),
      tracking_freshness: {
        stale: false, reasons: [], stale_after_days: 3, awaiting_update_count: 0,
        refresh_available_at: new Date(Date.now() + 53 * 60_000).toISOString(),
      },
    });
    wrap(<CourtTrackingCard caseItem={caseItem} hearings={[]} />);

    expect(screen.getByRole("button", { name: /^refresh$/i })).toBeDisabled();
    expect(screen.getByText(/Checked 7 minutes ago\. eCourts allows one check an hour per case -- try again after .* \(in 53 min\)\./)).toBeInTheDocument();
  });

  it("shows a disposed case as disposed, not as waiting for a date", () => {
    const caseItem = makeCase({
      last_fetched_at: daysAgo(0.5),
      tracking_freshness: { stale: false, reasons: [], stale_after_days: 3, awaiting_update_count: 0, refresh_available_at: null },
      disposal: { source: "ecourts", detail: "Contested--DISPOSED OF NO COSTS", order_id: null, order_date: null },
    });
    wrap(<CourtTrackingCard caseItem={caseItem} hearings={[]} />);
    expect(screen.getByText("Disposed")).toBeInTheDocument();
    expect(screen.getByText("None -- case disposed")).toBeInTheDocument();
  });
});

describe("Order Overview's next date", () => {
  const order = (nextDate: string): CourtOrder =>
    ({
      id: 3, order_number: "3", order_date: dateKey(-40), has_file: true, description: "",
      summary: {
        status: "no_directions", what_happened: "Listed for orders.", next_date: nextDate, next_date_purpose: "",
        petitioner_directions: [], respondent_directions: [], your_side_directions: null,
        other_side_directions: null, your_side_label: null, other_side_label: null,
      },
    }) as unknown as CourtOrder;

  it("greys out a passed date and points to the tracked next hearing", () => {
    // Production: "Next date: 17 Aug 2026" still shown a month later.
    wrap(<OrderOverviewCard orders={[order(dateKey(-37))]} currentNextHearing={`${dateKey(9)}T00:00:00Z`} />);
    expect(screen.getByText("(passed)")).toBeInTheDocument();
    expect(screen.getByText(/Current next hearing: .* \(Court Tracking\)/)).toBeInTheDocument();
  });

  it("keeps a future date as the next date", () => {
    wrap(<OrderOverviewCard orders={[order(dateKey(5))]} currentNextHearing={null} />);
    expect(screen.getByText("Next date:")).toBeInTheDocument();
    expect(screen.queryByText("(passed)")).not.toBeInTheDocument();
  });
});

describe("Case Overview", () => {
  it("keeps the contact and the billed client apart, and names both parties", () => {
    const caseItem = makeCase({
      user_party_role: "petitioner",
      parties: {
        petitioner: "S.Sashi Kumar", respondent: "The State of Telangana", source: "record",
        ours: "S.Sashi Kumar", opposing: "The State of Telangana",
      },
      client_contacts: [
        {
          id: 1, case: 28, name: "Karthik Bablu", email: null, phone: null, role: "primary", is_billing_contact: true,
          receive_case_updates: true, receive_payment_reminders: true, relation_type: "", relation_name: "", age: null,
          address: "", created_at: "",
        },
      ],
    });
    wrap(<CaseOverview case={caseItem} onEditDetails={() => {}} />);

    expect(screen.getByText("Primary Contact")).toBeInTheDocument();
    expect(screen.getByText("Karthik Bablu")).toBeInTheDocument();
    expect(screen.getByText("Client (billed)")).toBeInTheDocument();
    expect(screen.getByText(/Not linked/)).toBeInTheDocument();
    expect(screen.getByText("your client")).toBeInTheDocument();
    // The opposing party is derived, not "N/A".
    expect(screen.getAllByText("The State of Telangana")).toHaveLength(2);
  });
});
