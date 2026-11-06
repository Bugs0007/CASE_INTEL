import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const nav = vi.hoisted(() => ({
  search: new URLSearchParams(),
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "1" }),
  usePathname: () => "/cases/1",
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: nav.back }),
  useSearchParams: () => nav.search,
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  const fx = await import("../e2e/fixtures");
  return {
    ...actual,
    apiBlob: vi.fn(async () => {
      throw new Error("no file in tests");
    }),
    apiClient: vi.fn(async (path: string) => {
      if (path === "/cases/1/") return fx.caseDetail;
      if (path === "/cases/1/orders/") return fx.orders;
      if (path === "/hearings/") return fx.hearings;
      if (path === "/documents/") return fx.documents;
      if (path === "/case-events/") return fx.events;
      if (path === "/advocate-profile/") return { advocate_name: "T", contact_email: "t@example.com", default_fee_amount: "0" };
      return [];
    }),
  };
});

import CaseDetailPage from "@/app/(dashboard)/cases/[id]/page";

function setWindow(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true, writable: true });
  Object.defineProperty(window, "innerHeight", { value: height, configurable: true, writable: true });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CaseDetailPage />
    </QueryClientProvider>,
  );
}

async function loaded() {
  const hearings = await screen.findByRole("region", { name: "Hearings & orders" });
  await waitFor(() => expect(within(hearings).getAllByRole("listitem").length).toBeGreaterThan(0));
  return hearings;
}

beforeEach(() => {
  nav.search = new URLSearchParams();
  nav.push.mockClear();
  setWindow(1536, 864);
});

describe("rows per window height", () => {
  it.each([
    // Documents give up a row to the order-check line (a tracked case) at 960 and 760.
    [960, 5, 4, "month", true],
    [864, 4, 4, "month", false],
    [760, 3, 2, "week", false],
  ] as const)("at %ipx tall: %i hearings, %i documents, a %s, client updates %s", async (height, hearings, docs, calendar, clientUpdates) => {
    setWindow(1920, height);
    renderPage();
    const hearingsCard = await loaded();
    expect(within(hearingsCard).getAllByRole("listitem")).toHaveLength(hearings);

    const documentsCard = screen.getByRole("region", { name: "Documents" });
    await waitFor(() => expect(within(documentsCard).getAllByRole("listitem")).toHaveLength(docs));

    expect(screen.queryByRole("grid", { name: calendar === "month" ? "This month" : "This week" })).toBeInTheDocument();
    expect(screen.queryByRole("grid", { name: calendar === "month" ? "This week" : "This month" })).not.toBeInTheDocument();

    expect(!!screen.queryByRole("region", { name: "Client updates" })).toBe(clientUpdates);
  });

  it("the header and facts strip carry the six facts and the sync status", async () => {
    renderPage();
    await loaded();
    expect(screen.getByRole("heading", { level: 1, name: /Butham Srinivas/ })).toBeInTheDocument();
    expect(screen.getByText(/Court tracking synced 2h ago/)).toBeInTheDocument();
    for (const label of ["Court", "Stage", "Your side", "Client", "Filed", "CNR"]) {
      expect(screen.getAllByText(label, { exact: false }).length).toBeGreaterThan(0);
    }
    expect(screen.getByText("HBHC010234562026")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /All details/ })).toBeInTheDocument();
  });
});

describe("expand buttons", () => {
  it("every card has one; each opens a dialog, Esc closes it and focus goes back to the button", async () => {
    const user = userEvent.setup();
    setWindow(1920, 960);
    renderPage();
    await loaded();

    const expected = [
      "Order Overview",
      "Hearings & orders",
      "Calendar",
      "Next hearing",
      "Tasks & Deadlines",
      "Documents",
      "Fees & billing",
      "Client updates",
    ];
    for (const title of expected) {
      const button = await screen.findByRole("button", { name: `Expand ${title}` });
      await user.click(button);
      expect(await screen.findByRole("dialog", { name: title })).toBeInTheDocument();

      await user.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("dialog", { name: title })).not.toBeInTheDocument());
      expect(button).toHaveFocus();
    }
    // Eight dialogs in one test: ~4 s alone, so the default 5 s limit flaked under load.
  }, 20_000);

  it("View all opens the same dialog, and Details opens the full hearing card", async () => {
    const user = userEvent.setup();
    renderPage();
    const card = await loaded();
    await user.click(within(card).getByRole("button", { name: /View all 7/ }));
    const dialog = await screen.findByRole("dialog", { name: "Hearings & orders" });
    // Fee and travel forms live only here, on the row's Details.
    expect(within(dialog).queryByText(/Add charge|Record fee/)).not.toBeInTheDocument();
    await user.click(within(dialog).getAllByRole("button", { name: "Details" })[0]!);
    expect(within(dialog).getAllByRole("button", { name: "Details" })[0]).toHaveAttribute("aria-expanded", "true");
  });

  it("the hearings dialog filters", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Expand Hearings & orders" }));
    const dialog = await screen.findByRole("dialog", { name: "Hearings & orders" });
    expect(within(dialog).getAllByRole("button", { name: "Details" })).toHaveLength(7);
    await user.click(within(dialog).getByRole("button", { name: /^Upcoming/ }));
    expect(within(dialog).getAllByRole("button", { name: "Details" })).toHaveLength(1);
    await user.click(within(dialog).getByRole("button", { name: /^Orders/ }));
    expect(within(dialog).getAllByRole("button", { name: "Details" })).toHaveLength(2);
  });
});

describe("the viewer", () => {
  it("?doc=<id> opens it, with the case's documents on the left and Case Bot docked on the right", async () => {
    // A wide window: jsdom has no matchMedia, so say the 1024px query matches.
    window.matchMedia = ((query: string) => ({
      matches: query.includes("min-width"),
      media: query,
      onchange: null,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    // The docked Case Bot scrolls its thread into view, which jsdom lacks.
    Element.prototype.scrollIntoView = vi.fn();
    nav.search = new URLSearchParams("doc=1");
    renderPage();
    const viewer = await screen.findByRole("dialog", { name: /Document viewer: order_2026-01-20\.pdf/ });
    expect(await within(viewer).findByRole("complementary", { name: "Case documents" })).toBeInTheDocument();
    expect(within(viewer).getByRole("complementary", { name: "Case Bot" })).toBeInTheDocument();
    expect(within(viewer).getByRole("button", { name: /Back to case|Close viewer/ })).toBeInTheDocument();
    // @ts-expect-error -- put jsdom back as it was
    delete window.matchMedia;
  });

  it("clicking a document row opens it in the viewer (?doc=<id>)", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    const card = screen.getByRole("region", { name: "Documents" });
    await waitFor(() => expect(within(card).getAllByRole("listitem").length).toBeGreaterThan(0));
    await user.click(within(card).getByRole("button", { name: /representation_12-01-2026\.pdf/ }));
    expect(nav.push).toHaveBeenCalledWith("/cases/1?doc=2", { scroll: false });
  });

  it("the Case Bot button opens the most recent order with the bot docked", async () => {
    const user = userEvent.setup();
    renderPage();
    await loaded();
    await user.click(screen.getByRole("button", { name: "Case Bot" }));
    expect(nav.push).toHaveBeenCalledWith("/cases/1?doc=1", { scroll: false });
  });
});
