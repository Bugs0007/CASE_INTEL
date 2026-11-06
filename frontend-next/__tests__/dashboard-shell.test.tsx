import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

const mocks = vi.hoisted(() => ({
  search: new URLSearchParams(),
  pathname: "/dashboard",
  push: vi.fn(),
  calls: [] as string[],
  drafts: 0,
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => mocks.search,
  usePathname: () => mocks.pathname,
  useRouter: () => ({ push: mocks.push, replace: vi.fn(), back: vi.fn() }),
}));

// Every request the dashboard and sidebar make goes through apiClient, so
// answering by URL here is enough to count them.
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    apiClient: vi.fn(async (path: string) => {
      mocks.calls.push(path);
      if (path.startsWith("/cases/refresh-all")) return { job_id: null };
      if (path.startsWith("/cases/")) return [];
      if (path.startsWith("/hearings/")) return [];
      if (path.startsWith("/tasks/")) return [];
      if (path.startsWith("/documents/")) return [];
      if (path.startsWith("/dashboard/upcoming-hearings/")) return [];
      if (path.startsWith("/client-messages/") || path.includes("messages"))
        return Array.from({ length: mocks.drafts }, (_, i) => ({ id: i + 1 }));
      if (path.startsWith("/billing")) {
        return {
          as_of: "2026-11-05",
          aging: [],
          totals: { invoiced_amount: "0", invoiced_count: 0, pending_amount: "0", pending_count: 0 },
          clients: [],
          clients_total: 0,
          unassigned: [],
          unassigned_total: 0,
          uninvoiced_hearings: [],
          uninvoiced_hearings_total: 0,
        };
      }
      if (path.startsWith("/advocate-profile/")) return { advocate_name: "Bhagath Rao" };
      return [];
    }),
  };
});

import { Sidebar } from "@/components/layout/sidebar";
import { Menu, MenuItem, MenuList, MenuTrigger } from "@/components/ui/menu";
import { ViewToggle } from "@/components/dashboard/view-toggle";
import {
  dashboardViewKey,
  resolveInitialView,
  useDashboardView,
} from "@/hooks/use-dashboard-view";
import DashboardPage from "@/app/(dashboard)/dashboard/page";
import {
  RECENT_CASES_MAX,
  pushRecentCase,
  readRecentCases,
  recentCasesKey,
  removeRecentCase,
} from "@/lib/recent-cases";
import { formatBadge } from "@/hooks/use-review-count";
import { shortcutFor } from "@/lib/shortcuts";

const openNewCaseChooser = vi.fn();
const openUploadDocument = vi.fn();
vi.mock("@/providers/dialog-provider", () => ({
  useDialogs: () => ({
    openNewCaseChooser,
    openUploadDocument,
    openSearch: vi.fn(),
    openShortcuts: vi.fn(),
  }),
}));

function withClient(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("case_intel_username", "advocate1");
  mocks.search = new URLSearchParams();
  mocks.pathname = "/dashboard";
  mocks.calls = [];
  mocks.drafts = 0;
  openNewCaseChooser.mockClear();
  openUploadDocument.mockClear();
});

describe("which view opens", () => {
  it("URL first, then the saved choice, then the Briefing", () => {
    expect(resolveInitialView("map", "brief")).toBe("map");
    expect(resolveInitialView("brief", "map")).toBe("brief");
    expect(resolveInitialView(null, "map")).toBe("map");
    expect(resolveInitialView("nonsense", "map")).toBe("map");
    expect(resolveInitialView(null, null)).toBe("brief");
    expect(resolveInitialView("junk", "junk")).toBe("brief");
  });

  function Probe() {
    const { view, setView } = useDashboardView();
    return (
      <>
        <span data-testid="view">{view}</span>
        <button onClick={() => setView("map")}>to map</button>
      </>
    );
  }

  it("reads the URL over the saved choice", () => {
    window.localStorage.setItem(dashboardViewKey("advocate1"), "brief");
    mocks.search = new URLSearchParams("view=map");
    render(<Probe />);
    expect(screen.getByTestId("view")).toHaveTextContent("map");
  });

  it("falls back to the saved choice, then to the Briefing", () => {
    window.localStorage.setItem(dashboardViewKey("advocate1"), "map");
    const { unmount } = render(<Probe />);
    expect(screen.getByTestId("view")).toHaveTextContent("map");
    unmount();
    window.localStorage.clear();
    window.localStorage.setItem("case_intel_username", "advocate1");
    render(<Probe />);
    expect(screen.getByTestId("view")).toHaveTextContent("brief");
  });

  it("saves the choice and puts it in the address bar without navigating", async () => {
    const user = userEvent.setup();
    const replace = vi.spyOn(window.history, "replaceState");
    render(<Probe />);
    await user.click(screen.getByText("to map"));
    expect(screen.getByTestId("view")).toHaveTextContent("map");
    expect(window.localStorage.getItem(dashboardViewKey("advocate1"))).toBe("map");
    expect(replace).toHaveBeenCalled();
    expect(String(replace.mock.calls.at(-1)?.[2])).toContain("view=map");
    expect(mocks.push).not.toHaveBeenCalled();
    replace.mockRestore();
  });
});

describe("ViewToggle", () => {
  it("is a tablist; arrow keys move between the two tabs", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ViewToggle view="brief" onChange={onChange} />);
    const tabs = screen.getAllByRole("tab");
    expect(screen.getByRole("tablist", { name: "Dashboard view" })).toBeInTheDocument();
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    expect(tabs[1]).toHaveAttribute("aria-selected", "false");
    tabs[0].focus();
    await user.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("map");
  });

  it("arrow left from the map goes back to the briefing", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ViewToggle view="map" onChange={onChange} />);
    screen.getByRole("tab", { name: /Practice map/ }).focus();
    await user.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenCalledWith("brief");
  });
});

describe("the dashboard page", () => {
  it("switching views neither refetches nor shows a loader", async () => {
    const user = userEvent.setup();
    render(withClient(<DashboardPage />));

    expect(await screen.findByRole("heading", { name: "Dashboard", level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Briefing/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByTestId("dashboard-skeleton")).not.toBeInTheDocument();

    const before = [...mocks.calls];
    expect(before.length).toBeGreaterThan(0);

    await user.click(screen.getByRole("tab", { name: /Practice map/ }));
    expect(screen.getByRole("tab", { name: /Practice map/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard-skeleton")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Briefing/ }));
    expect(screen.queryByTestId("dashboard-skeleton")).not.toBeInTheDocument();
    expect(mocks.calls).toEqual(before);
  });

  it("greets by the first name of the advocate profile", async () => {
    render(withClient(<DashboardPage />));
    expect(await screen.findByRole("heading", { name: /^Good (morning|afternoon|evening), Bhagath\.$/ })).toBeInTheDocument();
  });

  it("a brand-new account reads calmly, not broken", async () => {
    render(withClient(<DashboardPage />));
    expect(await screen.findByText("No hearings in the next two weeks.")).toBeInTheDocument();
    expect(screen.getByText("Nothing is waiting on you.")).toBeInTheDocument();
    expect(screen.getByText(/Nothing has changed since your last visit/)).toBeInTheDocument();
  });
});

describe("Menu", () => {
  function Harness({ onSelect = vi.fn() }: { onSelect?: () => void }) {
    return (
      <div>
        <Menu>
          <MenuTrigger>First</MenuTrigger>
          <MenuList label="First menu">
            <MenuItem onSelect={onSelect}>Alpha</MenuItem>
            <MenuItem>Beta</MenuItem>
          </MenuList>
        </Menu>
        <Menu>
          <MenuTrigger>Second</MenuTrigger>
          <MenuList label="Second menu">
            <MenuItem>Gamma</MenuItem>
          </MenuList>
        </Menu>
        <button>outside</button>
      </div>
    );
  }

  it("opens with the right ARIA and closes on Escape, returning focus", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const trigger = screen.getByRole("button", { name: "First" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("menu", { name: "First menu" })).toBeInTheDocument();
    expect(screen.getAllByRole("menuitem")).toHaveLength(2);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("closes on an outside click", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "First" }));
    await user.click(screen.getByRole("button", { name: "outside" }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("closes when an item is chosen, after running it", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    await user.click(screen.getByRole("button", { name: "First" }));
    await user.click(screen.getByRole("menuitem", { name: "Alpha" }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("only one menu is open at a time", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "First" }));
    await user.click(screen.getByRole("button", { name: "Second" }));
    expect(screen.queryByRole("menu", { name: "First menu" })).not.toBeInTheDocument();
    expect(screen.getByRole("menu", { name: "Second menu" })).toBeInTheDocument();
  });

  it("arrow keys move between items", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "First" }));
    expect(screen.getByRole("menuitem", { name: "Alpha" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Beta" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Alpha" })).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("menuitem", { name: "Beta" })).toHaveFocus();
  });
});

describe("Sidebar", () => {
  it("has five tabs, Messages (not Client Messages), and no Documents or Clients tab", async () => {
    render(withClient(<Sidebar />));
    const nav = screen.getByRole("navigation", { name: "Main" });
    const labels = within(nav)
      .getAllByRole("link")
      .map((a) => a.textContent?.replace(/\d+\+?$/, "").trim());
    expect(labels).toEqual(["Dashboard", "Cases", "Calendar", "Messages", "Billing"]);
  });

  it("lights Cases on a case page and on /documents, and Billing on /clients", () => {
    for (const [path, tab] of [
      ["/cases/12", "Cases"],
      ["/documents", "Cases"],
      ["/clients", "Billing"],
      ["/billing", "Billing"],
    ] as const) {
      mocks.pathname = path;
      const { unmount } = render(withClient(<Sidebar />));
      const nav = screen.getByRole("navigation", { name: "Main" });
      const current = within(nav).getAllByRole("link").filter((a) => a.getAttribute("aria-current") === "page");
      expect(current.map((a) => a.textContent)).toEqual([expect.stringContaining(tab)]);
      unmount();
    }
  });

  it("hides the Messages badge at zero and shows the count otherwise", async () => {
    const { unmount } = render(withClient(<Sidebar />));
    await waitFor(() => expect(mocks.calls.some((c) => c.includes("messages"))).toBe(true));
    expect(screen.queryByTestId("messages-badge")).not.toBeInTheDocument();
    unmount();

    mocks.drafts = 3;
    render(withClient(<Sidebar />));
    expect(await screen.findByTestId("messages-badge")).toHaveTextContent("3");
  });

  it("caps the badge at 99+", () => {
    expect(formatBadge(5)).toBe("5");
    expect(formatBadge(99)).toBe("99");
    expect(formatBadge(100)).toBe("99+");
  });

  it("New menu offers New case and Upload document, wired to the existing dialogs", async () => {
    const user = userEvent.setup();
    render(withClient(<Sidebar />));
    await user.click(screen.getByRole("button", { name: /^New/ }));
    await user.click(screen.getByRole("menuitem", { name: /New case/ }));
    expect(openNewCaseChooser).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: /^New/ }));
    await user.click(screen.getByRole("menuitem", { name: /Upload document/ }));
    expect(openUploadDocument).toHaveBeenCalledTimes(1);
  });

  it("account menu opens with Settings and Log out", async () => {
    const user = userEvent.setup();
    render(withClient(<Sidebar />));
    await user.click(screen.getByRole("button", { name: "Account menu" }));
    expect(screen.getByRole("menuitem", { name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Log out" })).toBeInTheDocument();
    expect(screen.getByText("Signed in")).toBeInTheDocument();
  });

  it("shows recent cases, hides the section when empty", () => {
    const { unmount } = render(withClient(<Sidebar />));
    expect(screen.queryByRole("region", { name: "Recent cases" })).not.toBeInTheDocument();
    unmount();

    pushRecentCase("advocate1", { id: 7, title: "A very long case title v. Somebody" });
    render(withClient(<Sidebar />));
    const link = screen.getByRole("link", { name: /A very long case title/ });
    expect(link).toHaveAttribute("href", "/cases/7");
    expect(link).toHaveAttribute("title", "A very long case title v. Somebody");
  });
});

describe("recent cases", () => {
  it("dedupes, keeps the newest first and caps at four", () => {
    for (const id of [1, 2, 3, 4, 5]) pushRecentCase("u", { id, title: `Case ${id}` });
    expect(readRecentCases("u").map((c) => c.id)).toEqual([5, 4, 3, 2]);
    expect(readRecentCases("u")).toHaveLength(RECENT_CASES_MAX);

    pushRecentCase("u", { id: 3, title: "Case 3 renamed" });
    expect(readRecentCases("u")).toEqual([
      { id: 3, title: "Case 3 renamed" },
      { id: 5, title: "Case 5" },
      { id: 4, title: "Case 4" },
      { id: 2, title: "Case 2" },
    ]);
  });

  it("stores only id and title, per user", () => {
    pushRecentCase("alice", { id: 1, title: "One" });
    pushRecentCase("bob", { id: 2, title: "Two" });
    expect(JSON.parse(window.localStorage.getItem(recentCasesKey("alice"))!)).toEqual([{ id: 1, title: "One" }]);
    expect(readRecentCases("bob")).toEqual([{ id: 2, title: "Two" }]);
  });

  it("forgets an entry that turned out to be a 404", () => {
    pushRecentCase("u", { id: 1, title: "One" });
    pushRecentCase("u", { id: 2, title: "Two" });
    removeRecentCase("u", 1);
    expect(readRecentCases("u")).toEqual([{ id: 2, title: "Two" }]);
  });

  it("survives junk in storage", () => {
    window.localStorage.setItem(recentCasesKey("u"), "{not json");
    expect(readRecentCases("u")).toEqual([]);
    window.localStorage.setItem(recentCasesKey("u"), JSON.stringify([{ id: "x" }, null, { id: 1, title: "ok" }]));
    expect(readRecentCases("u")).toEqual([{ id: 1, title: "ok" }]);
  });
});

describe("keyboard shortcuts", () => {
  const key = (k: string, extra = {}) => ({ key: k, metaKey: false, ctrlKey: false, altKey: false, ...extra });
  const free = { typing: false, modalOpen: false };

  it("N, U and ? map to their actions", () => {
    expect(shortcutFor(key("n"), free)).toBe("new-case");
    expect(shortcutFor(key("N"), free)).toBe("new-case");
    expect(shortcutFor(key("u"), free)).toBe("upload");
    expect(shortcutFor(key("?"), free)).toBe("shortcuts");
  });

  it("Cmd/Ctrl+K opens search, even while typing", () => {
    expect(shortcutFor(key("k", { metaKey: true }), { typing: true, modalOpen: false })).toBe("search");
    expect(shortcutFor(key("k", { ctrlKey: true }), free)).toBe("search");
  });

  it("letters are ignored while typing, with a dialog open, or with a modifier", () => {
    expect(shortcutFor(key("n"), { typing: true, modalOpen: false })).toBeNull();
    expect(shortcutFor(key("u"), { typing: false, modalOpen: true })).toBeNull();
    expect(shortcutFor(key("n", { ctrlKey: true }), free)).toBeNull();
    expect(shortcutFor(key("x"), free)).toBeNull();
    expect(shortcutFor({ ...key("n"), repeat: true }, free)).toBeNull();
  });
});
