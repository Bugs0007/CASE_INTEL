import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import CasesPage from "@/app/(dashboard)/cases/page";
import { collapsedStorageKey, groupingStorageKey } from "@/hooks/use-cases-grouping";
import type { Case } from "@/types";

// "Group by court / client" on the Cases page: headers with counts, folding a
// group, and what is remembered. Only the data hooks are mocked; the page, the
// grouping rules and the group list run as they do in the app.
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

const client = (id: number, name: string) => ({ id, name, client_type: "individual" as const });

// Three at the High Court (spelled two ways), one at a family court, one with
// no court; two clients with two cases each. Case 3 needs attention.
const CASES: Case[] = [
  makeCase({ id: 1, title: "Alpha v. State", court_name: "Telangana High Court", client_detail: client(10, "Meera Nair") }),
  makeCase({ id: 2, title: "Bravo v. GHMC", court_name: " telangana  high court", client_detail: client(10, "Meera Nair") }),
  makeCase({
    id: 3,
    title: "Charlie v. Bank",
    court_name: "Telangana High Court",
    client_detail: client(11, "Rao & Sons"),
    needs_attention: true,
    next_hearing_date: "2099-01-05T00:00:00Z",
  }),
  makeCase({ id: 4, title: "Delta v. Delta", court_name: "Family Court, Secunderabad", client_detail: client(11, "Rao & Sons") }),
  makeCase({ id: 5, title: "Echo v. Echo", court_name: null, client_name: "" }),
];

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CasesPage />
    </QueryClientProvider>,
  );
}

// A group's header button (the cards inside have buttons of their own).
const toggleOf = (section: HTMLElement) => section.querySelector("h3 button") as HTMLButtonElement;
const toggles = () => screen.getAllByTestId("case-group").map(toggleOf);
const headers = () => toggles().map((b) => b.textContent);
const groupButton = (name: RegExp) => toggles().find((b) => name.test(b.textContent ?? ""))!;
// What the header controls; folded, it sits inside an inert (unreachable) wrapper.
const panelOf = (button: HTMLElement) => document.getElementById(button.getAttribute("aria-controls")!)!;
const isInert = (button: HTMLElement) => panelOf(button).closest("[inert]") !== null;

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  window.history.replaceState(null, "", "/cases");
  vi.mocked(useDeleteCase).mockReturnValue({ mutateAsync: vi.fn(), variables: undefined } as unknown as ReturnType<typeof useDeleteCase>);
  vi.mocked(useUpcomingHearings).mockReturnValue({ data: [] } as unknown as ReturnType<typeof useUpcomingHearings>);
  vi.mocked(useDocuments).mockReturnValue({ data: [] } as unknown as ReturnType<typeof useDocuments>);
  vi.mocked(useCases).mockReturnValue({ data: CASES, isLoading: false, error: null } as unknown as ReturnType<typeof useCases>);
});

describe("Cases page grouping", () => {
  it("with no grouping the page is one plain list, soonest hearing first, no groups", () => {
    renderPage();
    expect(screen.queryByTestId("case-groups")).not.toBeInTheDocument();
    expect(screen.queryByText("Needs Attention This Week")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("case-row")[0]).toHaveTextContent("Charlie v. Bank");
    expect(screen.getByRole("button", { name: "None", pressed: true })).toBeInTheDocument();
  });

  it("?group=court shows a header per court with its case count, the cases without a court last", () => {
    window.history.replaceState(null, "", "/cases?group=court");
    renderPage();

    const groups = screen.getAllByTestId("case-group");
    expect(groups).toHaveLength(3);
    // Soonest hearing first (the High Court has one), then by name, then "No court set".
    expect(headers()[0]).toMatch(/Telangana High Court\s*3 cases/);
    expect(headers()[1]).toMatch(/Family Court, Secunderabad\s*1 case/);
    expect(headers()[2]).toMatch(/No court set\s*1 case/);

    // The urgent case sits in its court's group; there is no separate Needs Attention section.
    expect(screen.queryByText("Needs Attention This Week")).not.toBeInTheDocument();
    expect(within(groups[0]).getByText("Charlie v. Bank")).toBeInTheDocument();
    expect(within(groups[0]).getByText("Alpha v. State")).toBeInTheDocument();
    expect(within(groups[1]).getByText("Delta v. Delta")).toBeInTheDocument();
    // Next hearing of the group, from the case that has one.
    expect(headers()[0]).toMatch(/Next: /);
    expect(headers()[1]).toMatch(/No upcoming hearing/);
    // Within a group the sort holds: the case with a hearing first.
    const rows = within(groups[0]).getAllByTestId("case-row").map((r) => r.textContent ?? "");
    expect(rows[0]).toContain("Charlie v. Bank");
    expect(rows.findIndex((t) => t.includes("Charlie v. Bank"))).toBeLessThan(rows.findIndex((t) => t.includes("Alpha v. State")));
  });

  it("grouped cards still work after switching to the Cards view", async () => {
    window.history.replaceState(null, "", "/cases?group=court");
    renderPage();
    expect(screen.getAllByTestId("case-row")).toHaveLength(5);
    await userEvent.click(screen.getByRole("button", { name: "Cards" }));
    expect(screen.queryByTestId("case-row")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("case-group")).toHaveLength(3);
    expect(screen.getByText("Delta v. Delta")).toBeInTheDocument();
  });

  it("?group=client groups on the linked client", () => {
    window.history.replaceState(null, "", "/cases?group=client");
    renderPage();
    expect(headers()[0]).toMatch(/Rao & Sons\s*2 cases/); // has the hearing
    expect(headers()[1]).toMatch(/Meera Nair\s*2 cases/);
    expect(headers()[2]).toMatch(/No client\s*1 case/);
  });

  it("a header folds and opens its group, and the fold is remembered", async () => {
    window.history.replaceState(null, "", "/cases?group=court");
    const first = renderPage();

    const high = groupButton(/Telangana High Court/);
    expect(high).toHaveAttribute("aria-expanded", "true");
    expect(isInert(high)).toBe(false);

    await userEvent.click(high);
    expect(high).toHaveAttribute("aria-expanded", "false");
    expect(isInert(high)).toBe(true); // folded cards are out of reach
    // The other groups are untouched.
    expect(groupButton(/Family Court/)).toHaveAttribute("aria-expanded", "true");
    expect(JSON.parse(window.localStorage.getItem(collapsedStorageKey(null, "court"))!)).toEqual(["n:telangana high court"]);

    // Leave and come back: still folded.
    first.unmount();
    renderPage();
    expect(groupButton(/Telangana High Court/)).toHaveAttribute("aria-expanded", "false");
    expect(groupButton(/Family Court/)).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(groupButton(/Telangana High Court/));
    expect(groupButton(/Telangana High Court/)).toHaveAttribute("aria-expanded", "true");
  });

  it("folded state is kept per grouping: folding a court does not fold a client", async () => {
    window.history.replaceState(null, "", "/cases?group=court");
    renderPage();
    await userEvent.click(groupButton(/Telangana High Court/));

    await userEvent.click(screen.getByRole("button", { name: "Client", pressed: false }));
    expect(toggles().map((b) => b.getAttribute("aria-expanded"))).toEqual(["true", "true", "true"]);
    expect(groupButton(/Rao & Sons/)).toHaveAttribute("aria-expanded", "true");

    await userEvent.click(screen.getByRole("button", { name: "Court", pressed: false }));
    expect(groupButton(/Telangana High Court/)).toHaveAttribute("aria-expanded", "false");
  });

  it("Collapse all folds every group, Expand all opens them again", async () => {
    window.history.replaceState(null, "", "/cases?group=court");
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Collapse all" }));
    expect(toggles().map((b) => b.getAttribute("aria-expanded"))).toEqual(["false", "false", "false"]);
    await userEvent.click(screen.getByRole("button", { name: "Expand all" }));
    expect(toggles().map((b) => b.getAttribute("aria-expanded"))).toEqual(["true", "true", "true"]);
    expect(screen.getByRole("button", { name: "Collapse all" })).toBeInTheDocument();
  });

  it("the Group by control puts the choice in the address bar and remembers it", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Court" }));
    expect(new URL(window.location.href).searchParams.get("group")).toBe("court");
    expect(window.localStorage.getItem(groupingStorageKey(null))).toBe("court");
    expect(screen.getAllByTestId("case-group")).toHaveLength(3);

    await userEvent.click(screen.getByRole("button", { name: "None" }));
    expect(new URL(window.location.href).searchParams.has("group")).toBe(false);
    expect(window.localStorage.getItem(groupingStorageKey(null))).toBe("none");
    expect(screen.queryByTestId("case-groups")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("case-row")).toHaveLength(5);
  });

  it("opens grouped the way it was left, and the address bar wins over that", () => {
    window.localStorage.setItem(groupingStorageKey(null), "client");
    const first = renderPage();
    expect(screen.getByText(/Cases by client/)).toBeInTheDocument();
    first.unmount();

    window.history.replaceState(null, "", "/cases?group=court");
    renderPage();
    expect(screen.getByText(/Cases by court/)).toBeInTheDocument();
  });

  it("groups what the search leaves, so the counts match what is shown", async () => {
    window.history.replaceState(null, "", "/cases?group=court");
    renderPage();
    await userEvent.type(screen.getByPlaceholderText("Search by case, client, or party"), "Alpha");
    const groups = screen.getAllByTestId("case-group");
    expect(groups).toHaveLength(1);
    expect(headers()[0]).toMatch(/Telangana High Court\s*1 case/);
  });

  it("says so when nothing matches, instead of showing empty groups", async () => {
    window.history.replaceState(null, "", "/cases?group=client");
    renderPage();
    await userEvent.type(screen.getByPlaceholderText("Search by case, client, or party"), "zzzz-no-such-case");
    expect(screen.queryByTestId("case-groups")).not.toBeInTheDocument();
    expect(screen.getByText("No cases found")).toBeInTheDocument();
  });
});
