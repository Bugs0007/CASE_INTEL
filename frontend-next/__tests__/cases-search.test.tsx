import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import CasesPage from "@/app/(dashboard)/cases/page";
import type { Case } from "@/types";

// The Cases tab search is entirely client-side (no backend search
// endpoint exists -- see core/views/case.py's get_base_queryset(), which
// only filters status/priority/case_type). This suite proves the search
// predicate itself: pasting a CNR into the search box must find the
// matching case, same as searching by case number/title/party already
// does. Only the data hooks are mocked -- CasesPage's real filtering
// logic runs unmodified.
vi.mock("@/hooks/use-cases", () => ({
  useCases: vi.fn(),
  useDeleteCase: vi.fn(),
}));
vi.mock("@/hooks/use-dashboard", () => ({
  useUpcomingHearings: vi.fn(),
}));
vi.mock("@/hooks/use-documents", () => ({
  useDocuments: vi.fn(),
}));
vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
// CaseCard calls useRouter() on every render (for its click-to-navigate
// handler) -- no real Next.js app router is mounted under vitest, so this
// needs a stub rather than the "invariant expected app router to be
// mounted" crash.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
}));

import { useCases, useDeleteCase } from "@/hooks/use-cases";
import { useUpcomingHearings } from "@/hooks/use-dashboard";
import { useDocuments } from "@/hooks/use-documents";

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: 1,
    case_number: "WP/1000/2026",
    title: "Ramesh Kumar vs. TSSPDCL",
    client_name: "",
    client_contacts: [],
    opposing_party: null,
    user_party_role: "unknown",
    case_type: null,
    status: "open",
    priority: "medium",
    filing_date: null,
    notes: null,
    created_at: "2026-01-01T00:00:00Z",
    document_count: 0,
    hearing_count: 0,
    thread_count: 0,
    conversation_count: 0,
    cnr_number: null,
    court_type: null,
    tracking_config: null,
    tracking_enabled: false,
    fetch_status: "never_fetched",
    last_fetched_at: null,
    needs_attention: false,
    next_hearing_date: null,
    fee_summary: {
      pending_amount: "0.00",
      pending_count: 0,
      invoiced_amount: "0.00",
      invoiced_count: 0,
      paid_amount: "0.00",
      paid_count: 0,
      outstanding_amount: "0.00",
      total_amount: "0.00",
    },
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
  vi.clearAllMocks();
  vi.mocked(useDeleteCase).mockReturnValue({
    mutateAsync: vi.fn(),
    variables: undefined,
  } as unknown as ReturnType<typeof useDeleteCase>);
  vi.mocked(useUpcomingHearings).mockReturnValue({ data: [] } as unknown as ReturnType<
    typeof useUpcomingHearings
  >);
  vi.mocked(useDocuments).mockReturnValue({ data: [] } as unknown as ReturnType<typeof useDocuments>);
});

describe("CasesPage search", () => {
  it("finds a case by pasting its CNR into the search box", async () => {
    const trackedByCnr = makeCase({
      id: 1,
      case_number: "WP/1000/2026",
      title: "Ramesh Kumar vs. TSSPDCL",
      cnr_number: "MHAU019999992024",
    });
    const unrelated = makeCase({
      id: 2,
      case_number: "WP/2000/2026",
      title: "Someone Else's Case",
      cnr_number: "DLHC012345678920",
    });
    vi.mocked(useCases).mockReturnValue({
      data: [trackedByCnr, unrelated],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCases>);

    renderWithClient(<CasesPage />);

    expect(screen.getByText("Someone Else's Case")).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText("Search by case, client, or party");
    await userEvent.type(searchInput, "MHAU019999992024");

    expect(screen.getByText("Ramesh Kumar vs. TSSPDCL")).toBeInTheDocument();
    expect(screen.queryByText("Someone Else's Case")).not.toBeInTheDocument();
  });

  it("search is case-insensitive on the CNR", async () => {
    const trackedByCnr = makeCase({
      id: 1,
      case_number: "WP/1000/2026",
      title: "Ramesh Kumar vs. TSSPDCL",
      cnr_number: "MHAU019999992024",
    });
    vi.mocked(useCases).mockReturnValue({
      data: [trackedByCnr],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCases>);

    renderWithClient(<CasesPage />);

    const searchInput = screen.getByPlaceholderText("Search by case, client, or party");
    await userEvent.type(searchInput, "mhau019999992024");

    expect(screen.getByText("Ramesh Kumar vs. TSSPDCL")).toBeInTheDocument();
  });

  it("a case with no CNR yet is unaffected by CNR search text", async () => {
    const noCnr = makeCase({
      id: 3,
      case_number: "WP/3000/2026",
      title: "No CNR Case",
      cnr_number: null,
    });
    vi.mocked(useCases).mockReturnValue({
      data: [noCnr],
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useCases>);

    renderWithClient(<CasesPage />);

    const searchInput = screen.getByPlaceholderText("Search by case, client, or party");
    await userEvent.type(searchInput, "MHAU019999992024");

    expect(screen.queryByText("No CNR Case")).not.toBeInTheDocument();
  });
});
