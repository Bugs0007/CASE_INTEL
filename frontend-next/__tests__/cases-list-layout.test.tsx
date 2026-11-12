import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import CasesPage from "@/app/(dashboard)/cases/page";
import { sortCases } from "@/components/cases/list/model";
import { viewStorageKey } from "@/components/cases/list/use-cases-view";
import type { Case } from "@/types";

vi.mock("@/hooks/use-cases", () => ({ useCases: vi.fn(), useDeleteCase: vi.fn() }));
vi.mock("@/hooks/use-dashboard", () => ({ useUpcomingHearings: vi.fn() }));
vi.mock("@/hooks/use-documents", () => ({ useDocuments: vi.fn() }));
vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/cases",
}));

import { useCases, useDeleteCase } from "@/hooks/use-cases";
import { useUpcomingHearings } from "@/hooks/use-dashboard";
import { useDocuments } from "@/hooks/use-documents";

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: 1,
    case_number: "WP/1000/2026",
    title: "Some Matter",
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
    order_sync: { state: "ok", last_checked_at: null, last_success_at: null, found: 0, downloaded: 0, reason: null },
    ...overrides,
  };
}

const failedSync = { state: "failed" as const, last_checked_at: null, last_success_at: null, found: 0, downloaded: 0, reason: "other" };

const CASES: Case[] = [
  makeCase({ id: 1, title: "Zulu v. State", document_count: 7, next_hearing_date: "2099-03-01T00:00:00Z" }),
  makeCase({ id: 2, title: "Alpha v. Bank" }), // no hearing
  makeCase({
    id: 3,
    title: "Mike v. Mike",
    next_hearing_date: "2099-01-01T00:00:00Z",
    client_detail: { id: 5, name: "Meera Nair", client_type: "individual" },
  }),
  makeCase({ id: 4, title: "Delta v. Delta", tracking_enabled: true, order_sync: failedSync }),
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CasesPage />
    </QueryClientProvider>,
  );
}

const rowTitles = () => screen.getAllByTestId("case-row").map((r) => r.querySelector("a")!.textContent);

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  // Cards are the default; these tests exercise the list, so choose it explicitly.
  window.localStorage.setItem(viewStorageKey(null), "list");
  window.history.replaceState(null, "", "/cases");
  vi.mocked(useDeleteCase).mockReturnValue({ mutateAsync: vi.fn(), variables: undefined } as unknown as ReturnType<typeof useDeleteCase>);
  vi.mocked(useUpcomingHearings).mockReturnValue({
    data: [{ case_id: 3, days_until: 3 }],
  } as unknown as ReturnType<typeof useUpcomingHearings>);
  vi.mocked(useDocuments).mockReturnValue({
    data: [{ case_id: 1 }, { case_id: 1 }],
  } as unknown as ReturnType<typeof useDocuments>);
  vi.mocked(useCases).mockReturnValue({ data: CASES, isLoading: false, error: null } as unknown as ReturnType<typeof useCases>);
});

describe("Cases default view", () => {
  it("opens on Cards when no view has been chosen", () => {
    window.localStorage.removeItem(viewStorageKey(null));
    renderPage();
    expect(screen.getByRole("button", { name: "Cards" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "List" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByTestId("case-row")).not.toBeInTheDocument();
    expect(screen.getByText("Zulu v. State")).toBeInTheDocument();
  });
});

describe("Cases list view", () => {
  it("renders a row per case with next hearing and document count, and no empty-client text", () => {
    renderPage();
    expect(screen.getAllByTestId("case-row")).toHaveLength(4);
    expect(screen.queryByText("No client or contact yet")).not.toBeInTheDocument();
    const zulu = screen.getAllByTestId("case-row").find((r) => r.textContent?.includes("Zulu"))!;
    expect(zulu).toHaveTextContent("1 Mar");
    expect(within(zulu).getByText("7")).toBeInTheDocument();
    expect(zulu).toHaveTextContent("2 docs failed");
    const mike = screen.getAllByTestId("case-row").find((r) => r.textContent?.includes("Mike"))!;
    expect(mike).toHaveTextContent("Meera Nair");
    expect(mike).toHaveTextContent("Hearing this week");
  });

  it("sorts by next hearing, soonest first, cases with no hearing last", () => {
    renderPage();
    expect(rowTitles()).toEqual(["Mike v. Mike", "Zulu v. State", "Alpha v. Bank", "Delta v. Delta"]);
  });

  it("sorts by title, and a past hearing sorts after upcoming ones but before none", async () => {
    renderPage();
    await userEvent.selectOptions(screen.getByLabelText("Sort by"), "title");
    expect(rowTitles()).toEqual(["Alpha v. Bank", "Delta v. Delta", "Mike v. Mike", "Zulu v. State"]);

    const out = sortCases(
      [
        makeCase({ id: 1, title: "none" }),
        makeCase({ id: 2, title: "past", next_hearing_date: "2001-01-01T00:00:00Z" }),
        makeCase({ id: 3, title: "soon", next_hearing_date: "2099-01-01T00:00:00Z" }),
      ],
      "hearing",
      "2026-11-12",
    );
    expect(out.map((c) => c.title)).toEqual(["soon", "past", "none"]);
  });

  it("the strip shows counts as chips; clicking filters, clicking again clears", async () => {
    renderPage();
    expect(screen.getByRole("button", { name: /Hearing this week/ })).toHaveTextContent("(1)");
    expect(screen.getByRole("button", { name: /Order check failed/ })).toHaveTextContent("(1)");
    expect(screen.getByRole("button", { name: /Documents failed/ })).toHaveTextContent("(1)");

    await userEvent.click(screen.getByRole("button", { name: /Order check failed/ }));
    expect(rowTitles()).toEqual(["Delta v. Delta"]);
    expect(screen.getByRole("button", { name: /Order check failed/ })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(screen.getByRole("button", { name: /Order check failed/ }));
    expect(screen.getAllByTestId("case-row")).toHaveLength(4);
  });

  it("the Cards view toggle switches the layout and is remembered", async () => {
    const first = renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Cards" }));
    expect(screen.queryByTestId("case-row")).not.toBeInTheDocument();
    expect(screen.getByText("Zulu v. State")).toBeInTheDocument();
    expect(screen.queryByText("No client or contact yet")).not.toBeInTheDocument();
    expect(window.localStorage.getItem(viewStorageKey(null))).toBe("cards");

    first.unmount();
    renderPage();
    expect(screen.getByRole("button", { name: "Cards" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByTestId("case-row")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "List" }));
    expect(screen.getAllByTestId("case-row")).toHaveLength(4);
  });

  it("group by still works in the list view", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Client" }));
    const groups = screen.getAllByTestId("case-group");
    expect(groups).toHaveLength(2);
    expect(within(groups[0]).getAllByTestId("case-row")).toHaveLength(1);
    expect(within(groups[1]).getAllByTestId("case-row")).toHaveLength(3);
  });
});
