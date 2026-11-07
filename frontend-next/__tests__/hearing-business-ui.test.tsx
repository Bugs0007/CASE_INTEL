import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// What the server answers, which the tests move on by hand.
const server = vi.hoisted(() => ({
  entries: [] as unknown[],
  dailyReads: 0,
  checkCalls: 0,
  cooldown: false,
}));

vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    apiClient: vi.fn(async (path: string, options?: { method?: string }) => {
      if (path === "/cases/1/daily-status/") {
        server.dailyReads += 1;
        return server.entries;
      }
      if (path === "/cases/1/orders/check/" && options?.method === "POST") {
        server.checkCalls += 1;
        if (server.cooldown) {
          throw new actual.APIError(429, { detail: "An order check just ran. Try again in a few minutes.", retry_after: 240 });
        }
        return { order_sync: { state: "queued", last_checked_at: null, last_success_at: null, found: 0, downloaded: 0, reason: null } };
      }
      return [];
    }),
  };
});

import { MobileCaseView, type MobileCaseViewProps } from "@/components/cases/mobile/mobile-case-view";
import { CompactHearings } from "@/components/cases/compact/compact-main";
import { HearingBusinessPreview, HearingBusinessSection } from "@/components/cases/hearing-business";
import { useHearingBusiness, type HearingBusinessCheck } from "@/hooks/use-hearing-business";
import { caseDetail } from "../e2e/fixtures";
import type { Case, Hearing } from "@/types";
import type { DailyStatusEntry } from "@/types/daily-status";

const TEXT = "Petitioner counsel present. Respondent counsel absent.\nMemo filed, stay is granted. Hence call on 19.11.2026.";

const ENTRY: DailyStatusEntry = {
  business_date: "2026-11-01",
  court_name: "Principal Junior Civil Judge",
  business_text: TEXT,
  next_purpose: "STAY",
  next_hearing_date: "2026-11-19",
  fetched_at: "2026-11-06T04:00:00Z",
};

const hearing = (id: number, hearing_date: string, extra: Partial<Hearing> = {}): Hearing =>
  ({
    id,
    case: 1,
    case_title: "Rao vs State",
    hearing_date,
    hearing_type: "other",
    hearing_type_display: "Other",
    location: "Principal Junior Civil Judge",
    judge: null,
    status: "completed",
    status_display: "Completed",
    notes: null,
    outcome: null,
    source: "ecourts",
    business_date: null,
    purpose: "Arguments",
    appearance_fees: [],
    travel_bookings: [],
    cause_list_status: "not_checked",
    cause_list_status_display: "",
    cause_list_item_number: "",
    cause_list_court_hall: "",
    cause_list_stage: "",
    cause_list_checked_at: null,
    order_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...extra,
  }) as Hearing;

// 7 Nov 2026 in India. One saved entry (1 Nov); 20 Oct is listed by the court
// but not saved; 1 Sep is not listed at all; 19 Nov is still ahead.
const HEARINGS = [
  hearing(14, "2026-11-19T00:00:00Z", { status: "scheduled", status_display: "Scheduled", purpose: "Stay" }),
  hearing(11, "2026-11-01T00:00:00Z", { business_date: "2026-11-01" }),
  hearing(12, "2026-10-20T00:00:00Z", { business_date: "2026-10-20" }),
  hearing(13, "2026-09-01T00:00:00Z"),
];

const DISTRICT = {
  ...caseDetail,
  court_type: "district",
  tracking_enabled: true,
  order_sync: { state: "ok", last_checked_at: null, last_success_at: null, found: 0, downloaded: 0, reason: null },
} as unknown as Case;

const HIGH_COURT = { ...DISTRICT, court_type: "high_court" } as Case;

const withState = (c: Case, state: string) => ({ ...c, order_sync: { ...c.order_sync, state } }) as Case;

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

const newClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const noop = () => {};

function mobileProps(caseItem: Case): MobileCaseViewProps {
  return {
    caseItem,
    caseId: 1,
    hearings: HEARINGS,
    hearingsLoading: false,
    orders: [],
    documents: [],
    docsLoading: false,
    latestDatedOrder: null,
    onViewOrder: noop,
    onAddHearing: noop,
    onEditHearing: noop,
    onDeleteHearing: noop,
    onUpload: noop,
    onGenerate: noop,
    onViewDocument: noop,
    onProcessDocument: noop,
    onDeleteDocument: noop,
    processPending: false,
    onEditDetails: noop,
    onOpenTracking: noop,
    onOpenDetails: noop,
    onOpenBot: noop,
    statusLine: null,
  };
}

async function openHearingsTab(caseItem: Case) {
  const user = userEvent.setup();
  const client = newClient();
  const view = render(
    <Providers client={client}>
      <MobileCaseView {...mobileProps(caseItem)} />
    </Providers>,
  );
  await user.click(screen.getByRole("tab", { name: "Hearings" }));
  return { user, client, view };
}

const row = (name: RegExp) => screen.getByRole("button", { name });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 7, 12, 0, 0)); // 7 Nov 2026, local time
  window.localStorage.clear();
  // The phone's tab bar is drawn into the top bar's slot, which the app shell owns.
  Element.prototype.scrollIntoView = vi.fn(); // jsdom has none; the tab bar scrolls the chosen tab into view
  const slot = document.createElement("div");
  slot.id = "mobile-subbar-slot";
  document.body.appendChild(slot);
  server.entries = [ENTRY];
  server.dailyReads = 0;
  server.checkCalls = 0;
  server.cooldown = false;
});

afterEach(() => {
  vi.useRealTimers();
  document.getElementById("mobile-subbar-slot")?.remove();
});

describe("phone: the hearing rows", () => {
  it("gives a passed hearing with a record a one-line preview, and no other row", async () => {
    await openHearingsTab(DISTRICT);
    const rowWithRecord = row(/1 Nov 2026/);
    const preview = await within(rowWithRecord).findByTestId("hearing-business-preview");
    // The line break is collapsed: it is one line of text, clamped by the CSS.
    expect(preview).toHaveTextContent("Petitioner counsel present. Respondent counsel absent. Memo filed, stay is granted.");
    expect(preview.querySelector(".truncate")).not.toBeNull();
    expect(rowWithRecord).toHaveAccessibleName(/What happened is saved/);

    expect(within(row(/20 Oct 2026/)).queryByTestId("hearing-business-preview")).toBeNull();
    expect(within(row(/1 Sep 2026/)).queryByTestId("hearing-business-preview")).toBeNull();
    expect(within(row(/19 Nov 2026/)).queryByTestId("hearing-business-preview")).toBeNull();
  });

  it("shows no previews for a High Court case and never asks for daily status", async () => {
    await openHearingsTab(HIGH_COURT);
    expect(screen.queryByTestId("hearing-business-preview")).toBeNull();
    expect(server.dailyReads).toBe(0);
  });
});

describe("phone: the hearing sheet", () => {
  it("shows the full text, the next purpose and the next hearing for a hearing with a record", async () => {
    const { user } = await openHearingsTab(DISTRICT);
    await user.click(row(/1 Nov 2026/));
    const sheet = screen.getByRole("dialog", { name: "Hearing details" });
    const section = await within(sheet).findByRole("region", { name: "What happened" });

    const text = within(section).getByText(/Petitioner counsel present\./);
    expect(text).toHaveTextContent(TEXT.replace("\n", " "), { normalizeWhitespace: true });
    expect(text.textContent).toContain("\n"); // line breaks kept...
    expect(text.className).toContain("whitespace-pre-line"); // ...and drawn
    expect(text.className).not.toContain("line-clamp");

    expect(within(section).getByText("Next purpose")).toBeInTheDocument();
    expect(within(section).getByText("STAY").className).toContain("amber"); // the coloured pill
    expect(within(section).getByText("Next hearing")).toBeInTheDocument();
    expect(within(section).getByText("19 Nov 2026")).toBeInTheDocument();
    expect(within(section).getByText(/In 12 days/)).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: "Check now" })).toBeNull();
  });

  it("enters with a rise and honours reduced motion", async () => {
    const { user } = await openHearingsTab(DISTRICT);
    await user.click(row(/1 Nov 2026/));
    const section = await screen.findByRole("region", { name: "What happened" });
    expect(section.className).toContain("animate-rise-in");
    expect(section.className).toContain("motion-reduce:animate-none");
  });

  it("says what happened is not saved yet for a listed date, with a Check now button", async () => {
    const { user } = await openHearingsTab(DISTRICT);
    await user.click(row(/20 Oct 2026/));
    const section = await screen.findByRole("region", { name: "What happened" });
    expect(section).toHaveTextContent("What happened is not saved yet.");
    expect(within(section).getByRole("button", { name: "Check now" })).toBeInTheDocument();
  });

  it("queues the order check when Check now is tapped", async () => {
    const { user } = await openHearingsTab(DISTRICT);
    await user.click(row(/20 Oct 2026/));
    await user.click(await screen.findByRole("button", { name: "Check now" }));
    await waitFor(() => expect(server.checkCalls).toBe(1));
  });

  it("shows 'Checking, this takes a minute' while the order check is queued or running", async () => {
    const { user } = await openHearingsTab(withState(DISTRICT, "running"));
    await user.click(row(/20 Oct 2026/));
    const section = await screen.findByRole("region", { name: "What happened" });
    expect(within(section).getByRole("status")).toHaveTextContent("Checking, this takes a minute");
    expect(within(section).queryByRole("button", { name: "Check now" })).toBeNull();
  });

  it("tells the advocate when the check is refused for the server's cooldown", async () => {
    server.cooldown = true;
    const { user } = await openHearingsTab(DISTRICT);
    await user.click(row(/20 Oct 2026/));
    await user.click(await screen.findByRole("button", { name: "Check now" }));
    expect(await screen.findByText("A check just ran. Try again in about 4 min.")).toBeInTheDocument();
    // The button is still there to try again later.
    expect(screen.getByRole("button", { name: "Check now" })).toBeInTheDocument();
  });

  it("says plainly when the court lists nothing for a passed date", async () => {
    const { user } = await openHearingsTab(DISTRICT);
    await user.click(row(/1 Sep 2026/));
    const section = await screen.findByRole("region", { name: "What happened" });
    expect(section).toHaveTextContent("The court lists no daily status for this date.");
    expect(within(section).queryByRole("button", { name: "Check now" })).toBeNull();
  });

  it("has no section for a hearing that is still ahead or for a High Court case", async () => {
    const district = await openHearingsTab(DISTRICT);
    await district.user.click(row(/19 Nov 2026/));
    expect(screen.queryByRole("region", { name: "What happened" })).toBeNull();
    district.view.unmount();

    const high = await openHearingsTab(HIGH_COURT);
    await high.user.click(row(/1 Nov 2026/));
    expect(screen.queryByRole("region", { name: "What happened" })).toBeNull();
  });
});

describe("HearingBusinessSection", () => {
  const check = (extra: Partial<HearingBusinessCheck> = {}): HearingBusinessCheck => ({
    canCheck: true,
    checking: false,
    checkedSince: false,
    note: null,
    request: vi.fn(),
    ...extra,
  });

  it("draws nothing for off and none", () => {
    const { container, rerender } = render(<HearingBusinessSection info={{ kind: "off" }} check={check()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<HearingBusinessSection info={{ kind: "none" }} check={check()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("covers loading, a failed read, a quiet entry and the not-saved states", async () => {
    const reload = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<HearingBusinessSection info={{ kind: "loading" }} check={check()} />);
    expect(screen.getByRole("status", { name: "Loading what happened" })).toBeInTheDocument();

    rerender(<HearingBusinessSection info={{ kind: "error" }} check={check()} onReload={reload} />);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(reload).toHaveBeenCalledOnce();

    rerender(
      <HearingBusinessSection
        info={{ kind: "entry", entry: { ...ENTRY, business_text: "", next_purpose: "", next_hearing_date: null } }}
        check={check()}
      />,
    );
    expect(screen.getByText("The court recorded no business for this date.")).toBeInTheDocument();
    expect(screen.queryByText("Next purpose")).toBeNull();

    // A tracked case can be checked; an untracked one has no button.
    rerender(<HearingBusinessSection info={{ kind: "missing" }} check={check({ checkedSince: true })} />);
    expect(screen.getByText(/Still not saved/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check now" })).toBeInTheDocument();
    rerender(<HearingBusinessSection info={{ kind: "missing" }} check={check({ canCheck: false })} />);
    expect(screen.queryByRole("button", { name: "Check now" })).toBeNull();
  });

  it("previews a record on one line, or says there was none", () => {
    const { rerender } = render(<HearingBusinessPreview entry={ENTRY} />);
    expect(screen.getByTestId("hearing-business-preview")).toHaveTextContent(
      "Petitioner counsel present. Respondent counsel absent. Memo filed, stay is granted. Hence call on 19.11.2026.",
    );
    rerender(<HearingBusinessPreview entry={{ ...ENTRY, business_text: "" }} />);
    expect(screen.getByTestId("hearing-business-preview")).toHaveTextContent("No business recorded");
  });
});

describe("desktop: the Hearings & orders card", () => {
  function renderCard(caseItem: Case) {
    const client = newClient();
    render(
      <Providers client={client}>
        <CompactHearings
          caseId={1}
          hearings={HEARINGS}
          orders={[]}
          rows={5}
          isLoading={false}
          onAddHearing={noop}
          onEditHearing={noop}
          onDeleteHearing={noop}
          onViewOrder={noop}
          caseItem={caseItem}
        />
      </Providers>,
    );
    return userEvent.setup();
  }

  it("opens what happened under a hearing row, by click or keyboard, and closes it again", async () => {
    const user = renderCard(DISTRICT);
    const toggle = await screen.findByRole("button", { name: "What happened on 1 Nov 2026" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("hearing-business")).toBeNull();

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const panel = document.getElementById(toggle.getAttribute("aria-controls")!)!;
    const section = within(panel).getByRole("region", { name: "What happened" });
    expect(section).toHaveTextContent("Petitioner counsel present.");
    expect(section).toHaveTextContent("Next purpose");
    expect(section).toHaveTextContent("STAY");
    expect(section).toHaveTextContent("19 Nov 2026");
    expect(section).toHaveTextContent("In 12 days");

    toggle.focus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("hearing-business")).toBeNull();
    await user.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps the collapsed row at 40px and gives rows with nothing to open an empty slot, not a button", async () => {
    renderCard(DISTRICT);
    const toggle = await screen.findByRole("button", { name: "What happened on 1 Nov 2026" });
    expect(toggle.parentElement!.className).toContain("h-10");
    // The hearing ahead has nothing to open: no button, same column.
    expect(screen.queryByRole("button", { name: /What happened on 19 Nov 2026/ })).toBeNull();
    // The rows that could have a record each have an expander (saved, not saved, not listed).
    expect(screen.getAllByRole("button", { name: /^What happened on / })).toHaveLength(3);
  });

  it("shows the not-saved-yet state with Check now, and the checking state, in the opened row", async () => {
    const user = renderCard(DISTRICT);
    await user.click(await screen.findByRole("button", { name: "What happened on 20 Oct 2026" }));
    expect(screen.getByRole("region", { name: "What happened" })).toHaveTextContent("What happened is not saved yet.");
    await user.click(screen.getByRole("button", { name: "Check now" }));
    await waitFor(() => expect(server.checkCalls).toBe(1));
  });

  it("shows 'Checking, this takes a minute' in the opened row while a check runs", async () => {
    const user = renderCard(withState(DISTRICT, "queued"));
    await user.click(await screen.findByRole("button", { name: "What happened on 20 Oct 2026" }));
    expect(screen.getByRole("status")).toHaveTextContent("Checking, this takes a minute");
  });

  it("is unchanged for a High Court case: no expanders and no daily-status request", async () => {
    renderCard(HIGH_COURT);
    await screen.findByText("1 Nov 2026");
    expect(screen.queryByRole("button", { name: /What happened on/ })).toBeNull();
    expect(server.dailyReads).toBe(0);
  });
});

describe("useHearingBusiness", () => {
  it("reads the entries again when the order check settles, and says so after one it started", async () => {
    const client = newClient();
    const { result, rerender } = renderHook(
      ({ caseItem }: { caseItem: Case }) => useHearingBusiness(caseItem, HEARINGS),
      { wrapper: wrapper(client), initialProps: { caseItem: DISTRICT } },
    );
    await waitFor(() => expect(server.dailyReads).toBe(1));
    expect(result.current.enabled).toBe(true);

    await act(async () => {
      result.current.check.request();
    });
    await waitFor(() => expect(server.checkCalls).toBe(1));

    // The case page re-reads the case while the check runs; it moves on to running, then finishes.
    rerender({ caseItem: withState(DISTRICT, "running") });
    expect(result.current.check.checking).toBe(true);
    expect(server.dailyReads).toBe(1);
    rerender({ caseItem: withState(DISTRICT, "ok") });
    await waitFor(() => expect(server.dailyReads).toBe(2));
    await waitFor(() => expect(result.current.check.checkedSince).toBe(true));
    expect(result.current.check.checking).toBe(false);
  });

  it("does not read the entries again for a check that was never active", async () => {
    const client = newClient();
    const { rerender } = renderHook(({ caseItem }: { caseItem: Case }) => useHearingBusiness(caseItem, HEARINGS), {
      wrapper: wrapper(client),
      initialProps: { caseItem: DISTRICT },
    });
    await waitFor(() => expect(server.dailyReads).toBe(1));
    rerender({ caseItem: withState(DISTRICT, "ok") });
    rerender({ caseItem: withState(DISTRICT, "failed") });
    expect(server.dailyReads).toBe(1);
  });

  it("is off and silent for a case that is not a district case", async () => {
    const client = newClient();
    const { result } = renderHook(() => useHearingBusiness(HIGH_COURT, HEARINGS), { wrapper: wrapper(client) });
    expect(result.current.enabled).toBe(false);
    expect(result.current.infoFor(HEARINGS[1])).toEqual({ kind: "off" });
    expect(server.dailyReads).toBe(0);
  });
});
