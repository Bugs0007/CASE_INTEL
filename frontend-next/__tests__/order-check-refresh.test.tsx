import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// The order check as the case page sees it: the API answers from this state,
// which the tests move on by hand the way the worker would.
const server = vi.hoisted(() => ({
  orderSync: { state: "queued" } as Record<string, unknown>,
  withNewOrder: false,
  caseReads: 0,
  retryCalls: 0,
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "1" }),
  usePathname: () => "/cases/1",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

// Poll fast so the test does not sit through 5-second intervals. The 5 s
// itself is pinned in the last test.
vi.mock("@/lib/order-sync", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/order-sync")>()),
  ORDER_SYNC_POLL_MS: 40,
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  const fx = await import("../e2e/fixtures");
  const arrived = {
    ...fx.documents[0]!,
    id: 99,
    filename: "order_arrived.pdf",
    display_name: "order_arrived.pdf",
    document_date: new Date().toISOString().slice(0, 10),
    created_at: new Date().toISOString(),
  };
  return {
    ...actual,
    apiBlob: vi.fn(async () => {
      throw new Error("no file in tests");
    }),
    apiClient: vi.fn(async (path: string, options?: { method?: string }) => {
      if (path === "/cases/1/") {
        server.caseReads += 1;
        return { ...fx.caseDetail, order_sync: { ...fx.caseDetail.order_sync, ...server.orderSync } };
      }
      if (path === "/cases/1/orders/check/" && options?.method === "POST") {
        server.retryCalls += 1;
        server.orderSync = { state: "queued", found: 0, downloaded: 0, reason: null };
        return { order_sync: { ...fx.caseDetail.order_sync, ...server.orderSync } };
      }
      if (path === "/cases/1/orders/") return fx.orders;
      if (path === "/hearings/") return fx.hearings;
      if (path === "/documents/") return server.withNewOrder ? [arrived, ...fx.documents] : fx.documents;
      if (path === "/case-events/") return fx.events;
      if (path === "/advocate-profile/") return { advocate_name: "T", contact_email: "t@example.com", default_fee_amount: "0" };
      return [];
    }),
  };
});

import CaseDetailPage from "@/app/(dashboard)/cases/[id]/page";
import { useRefreshTracking } from "@/hooks/use-case-tracking";
import { caseTrackingApi } from "@/lib/api/case-tracking";

function setWindow(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", { value: width, configurable: true, writable: true });
  Object.defineProperty(window, "innerHeight", { value: height, configurable: true, writable: true });
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <CaseDetailPage />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  server.orderSync = { state: "queued", found: 0, downloaded: 0, reason: null };
  server.withNewOrder = false;
  server.caseReads = 0;
  server.retryCalls = 0;
  setWindow(1920, 960);
});

const documentsCard = () => screen.getByRole("region", { name: "Documents" });
const hearingsCard = () => screen.getByRole("region", { name: "Hearings & orders" });

describe("an order check that finishes while the page is open", () => {
  it("says it is checking, then shows the new order without a reload, then stops polling", async () => {
    renderPage();
    await waitFor(() => expect(within(documentsCard()).getAllByRole("listitem").length).toBeGreaterThan(0));

    // Queued: both cards say so, and the new order is not there yet.
    await waitFor(() => {
      expect(within(documentsCard()).getByTestId("order-sync-status")).toHaveTextContent("Checking eCourts for orders…");
      expect(within(hearingsCard()).getByTestId("order-sync-status")).toHaveTextContent("Checking eCourts for orders…");
    });
    expect(within(documentsCard()).queryByRole("button", { name: /order_arrived\.pdf/ })).toBeNull();
    const readsWhileQueued = server.caseReads;
    await waitFor(() => expect(server.caseReads).toBeGreaterThan(readsWhileQueued)); // it is polling

    // The worker finishes and saves a PDF.
    server.withNewOrder = true;
    server.orderSync = { state: "ok", found: 3, downloaded: 3, reason: null, last_checked_at: new Date().toISOString() };

    expect(await within(documentsCard()).findByRole("button", { name: /order_arrived\.pdf/ })).toBeInTheDocument();
    expect(within(documentsCard()).getByTestId("order-sync-status")).toHaveTextContent(/Checked .*3 orders\./);
    expect(within(hearingsCard()).getByTestId("order-sync-status")).toHaveAttribute("data-state", "ok");

    // Settled: the polling stops.
    const settled = server.caseReads;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 250));
    });
    expect(server.caseReads).toBe(settled);
  });

  it("an ok check that found nothing says so and adds nothing", async () => {
    server.orderSync = { state: "ok", found: 0, downloaded: 0, reason: null, last_checked_at: new Date().toISOString() };
    renderPage();
    await waitFor(() =>
      expect(within(documentsCard()).getByTestId("order-sync-status")).toHaveTextContent(
        "No orders published for this case yet.",
      ),
    );
    const reads = server.caseReads;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 200));
    });
    expect(server.caseReads).toBe(reads); // never polled: it was not queued or running
  });
});

describe("a failed order check", () => {
  it("names the reason, offers Retry, and Retry queues a check and shows it checking", async () => {
    const user = userEvent.setup();
    server.orderSync = {
      state: "failed",
      found: 0,
      downloaded: 0,
      reason: "CAPTCHA not read",
      last_checked_at: new Date().toISOString(),
    };
    renderPage();
    await screen.findByRole("region", { name: "Documents" });
    const line = await within(documentsCard()).findByTestId("order-sync-status");
    expect(line).toHaveTextContent("Last check failed (CAPTCHA not read). Will retry.");

    await user.click(within(documentsCard()).getByRole("button", { name: "Retry order check" }));

    await waitFor(() => expect(server.retryCalls).toBe(1));
    await waitFor(() =>
      expect(within(documentsCard()).getByTestId("order-sync-status")).toHaveTextContent("Checking eCourts for orders…"),
    );
    expect(within(documentsCard()).queryByRole("button", { name: "Retry order check" })).toBeNull();
  });
});

describe("a tracking refresh", () => {
  it("re-reads the case, its documents and its orders", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const invalidated: unknown[][] = [];
    vi.spyOn(client, "invalidateQueries").mockImplementation(((filters: { queryKey: unknown[] }) => {
      invalidated.push(filters.queryKey);
      return Promise.resolve();
    }) as typeof client.invalidateQueries);
    vi.spyOn(caseTrackingApi, "refresh").mockResolvedValue({} as never);

    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useRefreshTracking(1), { wrapper });
    await act(async () => {
      await result.current.mutateAsync(false);
    });

    const roots = invalidated.map((key) => key.join("/"));
    expect(roots).toContain("cases/detail/1");
    expect(roots).toContain("documents/list");
    expect(roots).toContain("court-orders/list");
    expect(roots).toContain("hearings/list");
  });
});

describe("the polling interval", () => {
  it("is 5 seconds in the app", async () => {
    const actual = await vi.importActual<typeof import("@/lib/order-sync")>("@/lib/order-sync");
    expect(actual.ORDER_SYNC_POLL_MS).toBe(5000);
    expect(actual.isOrderSyncActive("queued")).toBe(true);
    expect(actual.isOrderSyncActive("running")).toBe(true);
    for (const state of ["never", "ok", "partial", "failed"] as const) {
      expect(actual.isOrderSyncActive(state)).toBe(false);
    }
  });
});
