import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CaseCalendarCard } from "@/components/calendar/case-calendar-card";
import type { CaseEvent, Hearing, Task } from "@/types";

vi.mock("@/lib/api/tasks", () => ({
  tasksApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));
vi.mock("@/lib/api/case-events", () => ({
  caseEventsApi: { list: vi.fn(), create: vi.fn(), update: vi.fn(), delete: vi.fn() },
}));

// Opening an order streams a PDF into a new window -- only the call matters.
const viewOrderMutate = vi.fn();
vi.mock("@/hooks/use-court-orders", () => ({
  useViewOrder: () => ({ mutate: viewOrderMutate, isPending: false, variables: undefined }),
}));

vi.mock("@/components/ui/toaster", () => ({
  showToast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}));

import { tasksApi } from "@/lib/api/tasks";
import { caseEventsApi } from "@/lib/api/case-events";

const CASE_ID = 7;

function makeHearing(overrides: Partial<Hearing> = {}): Hearing {
  return {
    id: 1,
    case: CASE_ID,
    case_title: "Rao vs State",
    hearing_date: "2026-11-06T00:00:00Z",
    hearing_type: "other",
    hearing_type_display: "Other",
    location: "Court Hall 4",
    judge: null,
    status: "scheduled",
    status_display: "Scheduled",
    notes: null,
    outcome: null,
    source: "ecourts",
    business_date: null,
    purpose: "FOR ADMISSION",
    appearance_fees: [],
    travel_bookings: [],
    cause_list_status: "not_checked",
    cause_list_status_display: "Not checked",
    cause_list_item_number: "",
    cause_list_court_hall: "",
    cause_list_stage: "",
    cause_list_checked_at: null,
    order_summary: null,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    ...overrides,
  };
}

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: 10,
    case: CASE_ID,
    case_title: "Rao vs State",
    case_number: "WP/1/2026",
    title: "File counter affidavit",
    description: null,
    status: "pending",
    kind: "order_direction",
    kind_display: "Court order direction",
    due_date: "2026-11-06",
    due_date_basis: "relative_to_order",
    due_date_basis_display: "Counted from the order date",
    source_order: 77,
    source_text: "Respondent to file counter within 4 weeks.",
    rule_key: "",
    trigger_date: null,
    needs_review: true,
    user_modified: false,
    completed_at: null,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    ...overrides,
  };
}

function makeEvent(overrides: Partial<CaseEvent> = {}): CaseEvent {
  return {
    id: 20,
    case: CASE_ID,
    case_title: "Rao vs State",
    case_number: "WP/1/2026",
    title: "Mediation sitting",
    event_type: "mediation",
    event_type_display: "Mediation",
    date: "2026-11-06",
    start_time: "15:00:00",
    end_time: "16:30:00",
    location: "Mediation centre",
    notes: "",
    status: "scheduled",
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
    ...overrides,
  };
}

function renderCard(props: Partial<React.ComponentProps<typeof CaseCalendarCard>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const onEditDetails = vi.fn();
  render(
    <QueryClientProvider client={queryClient}>
      <CaseCalendarCard
        caseId={CASE_ID}
        hearings={[makeHearing()]}
        partyRole="respondent"
        onEditDetails={onEditDetails}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onEditDetails };
}

/** The 6th of November in the month grid (its accessible name starts with the weekday). */
const dayButton = () => screen.findByRole("button", { name: /^Friday 6 November/ });

const realInnerWidth = window.innerWidth;

beforeEach(() => {
  vi.clearAllMocks();
  // Only Date is faked, so timers/promises (react-query, waitFor) still run.
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-04T10:00:00+05:30") });
  vi.mocked(tasksApi.list).mockResolvedValue([makeTask()]);
  vi.mocked(caseEventsApi.list).mockResolvedValue([makeEvent()]);
});

afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(window, "innerWidth", { value: realInnerWidth, configurable: true });
});

describe("CaseCalendarCard", () => {
  it("fetches only this case's tasks and events", async () => {
    renderCard();
    await dayButton();
    await waitFor(() => expect(tasksApi.list).toHaveBeenCalledWith({ case_id: CASE_ID }));
    expect(caseEventsApi.list).toHaveBeenCalledWith({ case_id: CASE_ID });
  });

  it("marks the day and lists the hearing, event and order deadline when it is selected", async () => {
    const user = userEvent.setup();
    renderCard();

    const day = await dayButton();
    await waitFor(() => expect(day).toHaveAccessibleName(/1 hearing, 1 event, 1 deadline/));
    await user.click(day);

    expect(screen.getByText("Friday, November 6")).toBeInTheDocument();
    expect(screen.getByText("FOR ADMISSION")).toBeInTheDocument();
    expect(screen.getByText("Mediation sitting")).toBeInTheDocument();
    expect(screen.getByText("3:00 PM – 4:30 PM")).toBeInTheDocument();
    expect(screen.getByText("File counter affidavit")).toBeInTheDocument();
  });

  it("shows how an order deadline's date was arrived at, and that it is a suggestion", async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(await dayButton());

    expect(await screen.findByText("Counted from the order date")).toBeInTheDocument();
    expect(screen.getByText("Suggested")).toBeInTheDocument();
    expect(screen.getByText(/Respondent to file counter within 4 weeks/)).toBeInTheDocument();
  });

  it("opens the source order from an order deadline", async () => {
    const user = userEvent.setup();
    renderCard();
    await user.click(await dayButton());

    await user.click(await screen.findByRole("button", { name: /view order/i }));
    expect(viewOrderMutate).toHaveBeenCalledWith(77, expect.any(Object));
  });

  it("offers no View order for a task that did not come from an order", async () => {
    vi.mocked(tasksApi.list).mockResolvedValue([
      makeTask({ kind: "manual", source_order: null, needs_review: false, due_date_basis: "", due_date_basis_display: "" }),
    ]);
    const user = userEvent.setup();
    renderCard();
    await user.click(await dayButton());

    await screen.findByText("File counter affidavit");
    expect(screen.queryByRole("button", { name: /view order/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Suggested")).not.toBeInTheDocument();
  });

  it("completes and dismisses through the same task endpoint the Tasks card uses", async () => {
    vi.mocked(tasksApi.update).mockResolvedValue(makeTask({ status: "completed" }));
    const user = userEvent.setup();
    renderCard();
    await user.click(await dayButton());

    await user.click(await screen.findByRole("button", { name: /mark "file counter affidavit" done/i }));
    await waitFor(() => expect(tasksApi.update).toHaveBeenCalledWith(10, { status: "completed" }));

    await user.click(screen.getByRole("button", { name: /dismiss "file counter affidavit"/i }));
    await waitFor(() => expect(tasksApi.update).toHaveBeenCalledWith(10, { status: "cancelled" }));
    expect(tasksApi.delete).not.toHaveBeenCalled();
  });

  it("confirming a suggestion clears needs_review", async () => {
    vi.mocked(tasksApi.update).mockResolvedValue(makeTask({ needs_review: false }));
    const user = userEvent.setup();
    renderCard();
    await user.click(await dayButton());

    await user.click(await screen.findByRole("button", { name: /confirm/i }));
    await waitFor(() => expect(tasksApi.update).toHaveBeenCalledWith(10, { needs_review: false }));
  });

  describe("your side", () => {
    it("says order deadlines wait for it, and opens Edit Details", async () => {
      const user = userEvent.setup();
      const { onEditDetails } = renderCard({ partyRole: "unknown" });

      expect(
        await screen.findByText(/order deadlines appear here once your side \(petitioner or respondent\) is set/i),
      ).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: /set your side/i }));
      expect(onEditDetails).toHaveBeenCalledTimes(1);
    });

    it.each(["petitioner", "respondent"] as const)("is quiet once the side is %s", async (partyRole) => {
      renderCard({ partyRole });
      await dayButton();
      expect(screen.queryByText(/order deadlines appear here/i)).not.toBeInTheDocument();
    });
  });

  describe("adding an event", () => {
    it("pre-fills the selected day and saves a timed event for this case", async () => {
      vi.mocked(caseEventsApi.create).mockResolvedValue(makeEvent({ id: 21 }));
      const user = userEvent.setup();
      renderCard();

      await user.click(await dayButton());
      await user.click(screen.getByRole("button", { name: /add event/i }));

      const dialog = await screen.findByRole("dialog");
      expect(within(dialog).getByLabelText(/^date/i)).toHaveValue("2026-11-06");

      await user.type(within(dialog).getByLabelText(/^title/i), "Call with client");
      await user.selectOptions(within(dialog).getByLabelText(/^type/i), "client_call");
      await user.click(within(dialog).getByLabelText(/all day/i));
      await user.type(within(dialog).getByLabelText(/^starts/i), "10:30");
      await user.type(within(dialog).getByLabelText(/^ends/i), "11:00");
      await user.click(within(dialog).getByRole("button", { name: /^add event$/i }));

      await waitFor(() =>
        expect(caseEventsApi.create).toHaveBeenCalledWith(
          expect.objectContaining({
            case: CASE_ID,
            title: "Call with client",
            event_type: "client_call",
            date: "2026-11-06",
            start_time: "10:30",
            end_time: "11:00",
            status: "scheduled",
          }),
        ),
      );
    });

    it("saves an all-day event with no times", async () => {
      vi.mocked(caseEventsApi.create).mockResolvedValue(makeEvent({ id: 21 }));
      const user = userEvent.setup();
      renderCard();

      await user.click(await screen.findByRole("button", { name: /add event/i }));
      const dialog = await screen.findByRole("dialog");
      await user.type(within(dialog).getByLabelText(/^title/i), "Site visit");
      await user.click(within(dialog).getByRole("button", { name: /^add event$/i }));

      await waitFor(() =>
        expect(caseEventsApi.create).toHaveBeenCalledWith(
          expect.objectContaining({ title: "Site visit", start_time: null, end_time: null }),
        ),
      );
    });

    it("refuses an end time at or before the start without calling the API", async () => {
      const user = userEvent.setup();
      renderCard();

      await user.click(await screen.findByRole("button", { name: /add event/i }));
      const dialog = await screen.findByRole("dialog");
      await user.type(within(dialog).getByLabelText(/^title/i), "Hearing prep");
      await user.click(within(dialog).getByLabelText(/all day/i));
      await user.type(within(dialog).getByLabelText(/^starts/i), "11:00");
      await user.type(within(dialog).getByLabelText(/^ends/i), "10:00");
      await user.click(within(dialog).getByRole("button", { name: /^add event$/i }));

      expect(await within(dialog).findByText(/end time must be after the start time/i)).toBeInTheDocument();
      expect(caseEventsApi.create).not.toHaveBeenCalled();
    });

    it("edits and deletes an existing event", async () => {
      vi.mocked(caseEventsApi.update).mockResolvedValue(makeEvent({ title: "Mediation, rescheduled" }));
      vi.mocked(caseEventsApi.delete).mockResolvedValue(undefined);
      vi.spyOn(window, "confirm").mockReturnValue(true);
      const user = userEvent.setup();
      renderCard();

      await user.click(await dayButton());
      await user.click(await screen.findByRole("button", { name: /^edit$/i }));
      const dialog = await screen.findByRole("dialog");

      const title = within(dialog).getByLabelText(/^title/i);
      expect(title).toHaveValue("Mediation sitting");
      expect(within(dialog).getByLabelText(/^starts/i)).toHaveValue("15:00");
      await user.clear(title);
      await user.type(title, "Mediation, rescheduled");
      await user.click(within(dialog).getByRole("button", { name: /save changes/i }));
      await waitFor(() =>
        expect(caseEventsApi.update).toHaveBeenCalledWith(
          20,
          expect.objectContaining({ title: "Mediation, rescheduled", start_time: "15:00", end_time: "16:30" }),
        ),
      );

      await user.click(await screen.findByRole("button", { name: /^edit$/i }));
      await user.click(within(await screen.findByRole("dialog")).getByRole("button", { name: /^delete$/i }));
      await waitFor(() => expect(caseEventsApi.delete).toHaveBeenCalledWith(20));
    });
  });

  describe("on a phone", () => {
    it("defaults to the agenda: the next 30 days, grouped by day", async () => {
      Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
      vi.mocked(tasksApi.list).mockResolvedValue([
        makeTask({ due_date: "2026-11-06" }),
        makeTask({ id: 11, title: "Far away", due_date: "2026-12-20" }),
      ]);
      renderCard();

      const nov6 = await screen.findByRole("region", { name: /friday 6 november/i });
      expect(await within(nov6).findByText("Mediation sitting")).toBeInTheDocument();
      expect(await within(nov6).findByText("File counter affidavit")).toBeInTheDocument();
      expect(screen.queryByText("Far away")).not.toBeInTheDocument(); // past the 30 days
      expect(screen.queryByRole("button", { name: /^Friday 6 November/ })).not.toBeInTheDocument();
    });

    it("can switch to the month grid and back", async () => {
      Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
      const user = userEvent.setup();
      renderCard();

      await screen.findByRole("region", { name: /friday 6 november/i });
      await user.click(screen.getByRole("button", { name: "Month" }));
      expect(await dayButton()).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Agenda" }));
      expect(await screen.findByRole("region", { name: /friday 6 november/i })).toBeInTheDocument();
    });

    it("says so when the next 30 days are empty", async () => {
      Object.defineProperty(window, "innerWidth", { value: 390, configurable: true });
      vi.mocked(tasksApi.list).mockResolvedValue([]);
      vi.mocked(caseEventsApi.list).mockResolvedValue([]);
      renderCard({ hearings: [] });

      expect(await screen.findByText(/nothing in the next 30 days/i)).toBeInTheDocument();
    });
  });

  it("uses the month grid at desktop width", async () => {
    Object.defineProperty(window, "innerWidth", { value: 1280, configurable: true });
    renderCard();
    expect(await dayButton()).toBeInTheDocument();
  });
});
