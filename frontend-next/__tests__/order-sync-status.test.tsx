import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  OrderSyncStatusLine,
  describeOrderSync,
  orderCheckMarker,
} from "@/components/cases/order-sync-status";
import { CaseCard } from "@/components/cases/case-card";
import type { Case, OrderSyncStatus } from "@/types";

// CaseCard calls useRouter() on every render; no app router under vitest.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
}));

const HOURS_AGO = (h: number) => new Date(Date.now() - h * 3600_000).toISOString();

function sync(overrides: Partial<OrderSyncStatus> = {}): OrderSyncStatus {
  return {
    state: "ok",
    last_checked_at: HOURS_AGO(3),
    last_success_at: HOURS_AGO(3),
    found: 0,
    downloaded: 0,
    reason: null,
    ...overrides,
  };
}

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: 7,
    case_number: "OS/336/2026",
    title: "A vs B",
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
    hearing_count: 2,
    thread_count: 0,
    conversation_count: 0,
    cnr_number: "TSHC010030082026",
    court_type: "district",
    tracking_config: null,
    tracking_enabled: true,
    fetch_status: "success",
    last_fetched_at: null,
    needs_attention: false,
    next_hearing_date: null,
    fee_summary: {} as Case["fee_summary"],
    order_sync: sync(),
    ...overrides,
  } as Case;
}

describe("describeOrderSync", () => {
  it("never ran", () => {
    expect(describeOrderSync(sync({ state: "never", last_checked_at: null }), true)).toEqual({
      text: "Orders not checked yet",
      tone: "muted",
    });
  });

  it("says nothing for an untracked case that was never checked", () => {
    expect(describeOrderSync(sync({ state: "never" }), false)).toBeNull();
  });

  it("queued and running show a busy line", () => {
    expect(describeOrderSync(sync({ state: "queued" }), true)).toMatchObject({ busy: true, tone: "muted" });
    expect(describeOrderSync(sync({ state: "running" }), true)?.text).toMatch(/Checking the court portal/);
  });

  it("ok with nothing found says so plainly instead of a bare zero", () => {
    const line = describeOrderSync(sync({ state: "ok", found: 0 }), true);
    expect(line?.text).toMatch(/^No orders found on the court portal · checked (about )?3 hours ago/);
    expect(line?.tone).toBe("muted");
  });

  it("ok with orders reports when it was checked and how many", () => {
    const line = describeOrderSync(sync({ state: "ok", found: 3, downloaded: 3 }), true);
    expect(line?.text).toBe("Orders last checked about 3 hours ago · 3 orders found");
  });

  it("partial is amber and says what was saved", () => {
    const line = describeOrderSync(sync({ state: "partial", found: 3, downloaded: 1, reason: "CAPTCHA not read" }), true);
    expect(line).toMatchObject({ tone: "warning" });
    expect(line?.text).toMatch(/^3 orders found, 1 downloaded/);
  });

  it("failed is amber, names the mapped reason, and promises a retry", () => {
    const line = describeOrderSync(
      sync({ state: "failed", reason: "CAPTCHA not read", last_success_at: HOURS_AGO(48) }),
      true,
    );
    expect(line?.tone).toBe("warning");
    expect(line?.text).toContain("Last order check failed (CAPTCHA not read), retries on next refresh");
    expect(line?.text).toContain("last successful check");
  });

  it("failed with no earlier success omits the last-success clause; 'other' reads as unexpected", () => {
    const line = describeOrderSync(sync({ state: "failed", reason: "other", last_success_at: null }), true);
    expect(line?.text).toBe("Last order check failed (unexpected error), retries on next refresh");
  });
});

describe("orderCheckMarker (Cases card)", () => {
  it("failed and partial are always flagged for a tracked case", () => {
    expect(orderCheckMarker(makeCase({ order_sync: sync({ state: "failed" }) }))).toBe("order check failed");
    expect(orderCheckMarker(makeCase({ order_sync: sync({ state: "partial" }), document_count: 1 }))).toBe(
      "orders partly fetched",
    );
  });

  it("never-checked is flagged only while the doc count is a bare zero", () => {
    const never = sync({ state: "never", last_checked_at: null });
    expect(orderCheckMarker(makeCase({ order_sync: never, document_count: 0 }))).toBe("orders not checked");
    expect(orderCheckMarker(makeCase({ order_sync: never, document_count: 4 }))).toBeNull();
  });

  it("a clean check, and any untracked case, show no marker", () => {
    expect(orderCheckMarker(makeCase())).toBeNull();
    expect(orderCheckMarker(makeCase({ tracking_enabled: false, order_sync: sync({ state: "failed" }) }))).toBeNull();
  });
});

describe("rendering", () => {
  it("the card keeps the docs count and adds the amber marker when the check failed", () => {
    render(<CaseCard case={makeCase({ order_sync: sync({ state: "failed", reason: "CAPTCHA not read" }) })} />);
    expect(screen.getByText("0 docs")).toBeInTheDocument();
    expect(screen.getByTestId("order-check-marker")).toHaveTextContent("order check failed");
  });

  it("the card shows no marker after a clean check that found nothing", () => {
    render(<CaseCard case={makeCase()} />);
    expect(screen.getByText("0 docs")).toBeInTheDocument();
    expect(screen.queryByTestId("order-check-marker")).toBeNull();
  });

  it.each([
    ["never", "Orders not checked yet"],
    ["queued", "Order check queued…"],
    ["running", "Checking the court portal for orders…"],
    ["ok", "No orders found on the court portal"],
    ["partial", "orders found, 1 downloaded"],
    ["failed", "Last order check failed (court portal didn't answer), retries on next refresh"],
  ] as const)("the case page line for state %s", (state, text) => {
    render(
      <OrderSyncStatusLine
        caseItem={makeCase({
          order_sync: sync({ state, found: state === "partial" ? 3 : 0, downloaded: 1, reason: "court portal didn't answer" }),
        })}
      />,
    );
    const line = screen.getByTestId("order-sync-status");
    expect(line).toHaveAttribute("data-state", state);
    expect(line).toHaveTextContent(text);
  });

  it("renders nothing for an untracked case that was never checked", () => {
    render(
      <OrderSyncStatusLine
        caseItem={makeCase({ tracking_enabled: false, order_sync: sync({ state: "never" }) })}
      />,
    );
    expect(screen.queryByTestId("order-sync-status")).toBeNull();
  });
});
