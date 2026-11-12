import { useState } from "react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PracticeWeekCalendar } from "@/components/dashboard/practice/practice-week-calendar";
import { PortfolioSummary } from "@/components/dashboard/practice/portfolio-summary";
import { entryHref, referenceHref } from "@/components/dashboard/practice/routes";
import {
  FIXTURE_DAY,
  FIXTURE_WEEK_START,
  emptyCalendar,
  sampleCalendar,
  samplePortfolio,
} from "@/components/dashboard/practice/fixtures";
import type { PracticeCalendarWindow } from "@/types/practice";

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-11T10:00:00+05:30") });
});
afterEach(() => vi.useRealTimers());

function Harness({
  calendar = sampleCalendar,
  loading = false,
  error = false,
  onRetry = () => {},
  onAskAboutDay = () => {},
  onWeekChange = () => {},
}: {
  calendar?: PracticeCalendarWindow | null;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  onAskAboutDay?: (day: string) => void;
  onWeekChange?: (weekStart: string) => void;
}) {
  const [day, setDay] = useState(FIXTURE_DAY);
  return (
    <PracticeWeekCalendar
      calendar={calendar}
      loading={loading}
      error={error}
      onRetry={onRetry}
      weekStart={FIXTURE_WEEK_START}
      onWeekChange={onWeekChange}
      selectedDay={day}
      onSelectDay={setDay}
      onAskAboutDay={onAskAboutDay}
    />
  );
}

describe("PracticeWeekCalendar", () => {
  it("draws markers that match the fixture counts and marks today", () => {
    render(<Harness />);
    expect(
      screen.getByRole("button", { name: "Wednesday 11 November, today, 1 hearing, 1 event, 1 deadline" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thursday 12 November, 1 hearing" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Monday 9 November, nothing scheduled" })).toBeInTheDocument();
  });

  it("changes the agenda when another day is selected", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const agenda = () => within(screen.getByRole("region", { name: /^Agenda for/ }));
    expect(agenda().getByText("Mediation sitting")).toBeInTheDocument();
    expect(agenda().queryByText("Hearing: arguments")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /^Thursday 12 November/ }));
    expect(agenda().getByText("Hearing: arguments")).toBeInTheDocument();
    expect(agenda().queryByText("Mediation sitting")).not.toBeInTheDocument();
  });

  it("groups a day in hearing, event, deadline order with times, status and review flags", () => {
    render(<Harness />);
    const agenda = within(screen.getByRole("region", { name: /^Agenda for/ }));
    const headings = agenda.getAllByRole("heading", { level: 5 }).map((h) => h.textContent);
    expect(headings).toEqual(["Hearings", "Events", "Deadlines"]);
    expect(agenda.getByText("3:00 PM – 4:30 PM")).toBeInTheDocument();
    expect(agenda.getByText("Needs review")).toBeInTheDocument();
    expect(agenda.getAllByText("Rao vs State")).toHaveLength(3);
  });

  it("shows completed status and falls back to /calendar for a row with no case", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: /^Thursday 12 November/ }));
    expect(screen.getByText("Completed")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /Hearing: arguments/ });
    expect(link).toHaveAttribute("href", "/calendar");
    expect(screen.getByRole("link", { name: /Send client update/ })).toHaveAttribute("href", "/cases/7");
  });

  it("links to the full calendar", () => {
    render(<Harness />);
    expect(screen.getByRole("link", { name: "Open full calendar" })).toHaveAttribute("href", "/calendar");
  });

  it("prefills through onAskAboutDay and sends nothing itself", async () => {
    const user = userEvent.setup();
    const onAskAboutDay = vi.fn();
    render(<Harness onAskAboutDay={onAskAboutDay} />);
    await user.click(screen.getByRole("button", { name: /^Thursday 12 November/ }));
    await user.click(screen.getByRole("button", { name: "Ask about this day" }));
    expect(onAskAboutDay).toHaveBeenCalledTimes(1);
    expect(onAskAboutDay).toHaveBeenCalledWith("2026-11-12");
  });

  it("moves the week with the previous and next controls", async () => {
    const user = userEvent.setup();
    const onWeekChange = vi.fn();
    render(<Harness onWeekChange={onWeekChange} />);
    await user.click(screen.getByRole("button", { name: "Next week" }));
    await user.click(screen.getByRole("button", { name: "Previous week" }));
    expect(onWeekChange).toHaveBeenNthCalledWith(1, "2026-11-16");
    expect(onWeekChange).toHaveBeenNthCalledWith(2, "2026-11-02");
  });

  it("shows the last-updated time in India time", () => {
    render(<Harness />);
    expect(screen.getByText(/^Updated 3:05 pm$/i)).toBeInTheDocument();
  });

  it("shows a loading state", () => {
    render(<Harness calendar={null} loading />);
    expect(screen.getByText("Loading your calendar.")).toBeInTheDocument();
  });

  it("says so when the week is empty", () => {
    render(<Harness calendar={emptyCalendar} />);
    expect(screen.getByText("Nothing is scheduled this week.")).toBeInTheDocument();
  });

  it("says so when only the selected day is empty", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: /^Monday 9 November/ }));
    expect(screen.getByText("Nothing is scheduled on this day.")).toBeInTheDocument();
  });

  it("shows an error with a retry", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<Harness calendar={null} error onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The calendar could not be loaded.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("warns when the window is truncated", () => {
    render(<Harness calendar={{ ...sampleCalendar, truncated: true, total: 240 }} />);
    expect(screen.getByText(/Showing 5 of 240 items/)).toBeInTheDocument();
  });
});

describe("PortfolioSummary", () => {
  it("shows the exact totals and the case rows", () => {
    render(<PortfolioSummary snapshot={samplePortfolio} loading={false} error={false} onRetry={() => {}} onPageChange={() => {}} />);
    const stat = (label: string) => screen.getByText(label).nextElementSibling;
    expect(stat("Total cases")).toHaveTextContent("16");
    expect(stat("Active")).toHaveTextContent("12");
    expect(stat("With a next hearing")).toHaveTextContent("9");
    expect(stat("No date scheduled")).toHaveTextContent("3");
    const statuses = within(screen.getByRole("list", { name: "Cases by status" }));
    expect(statuses.getByText("Open 12")).toBeInTheDocument();
    expect(statuses.getByText("Closed 3")).toBeInTheDocument();
    const rao = screen.getByRole("link", { name: /Rao vs State/ });
    expect(rao).toHaveAttribute("href", "/cases/7");
    expect(rao).toHaveTextContent("Telangana High Court");
    expect(rao).toHaveTextContent("Next hearing 11 Nov 2026");
    expect(screen.getByRole("link", { name: /Sharma vs Kumar/ })).toHaveTextContent("No next hearing");
    expect(screen.getByRole("link", { name: "Open all cases" })).toHaveAttribute("href", "/cases");
  });

  it("pages with onPageChange from the matching total, not the row count", async () => {
    const user = userEvent.setup();
    const onPageChange = vi.fn();
    render(<PortfolioSummary snapshot={samplePortfolio} loading={false} error={false} onRetry={() => {}} onPageChange={onPageChange} />);
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Next page" }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it("has loading, empty and error states", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = render(<PortfolioSummary snapshot={null} loading error={false} onRetry={onRetry} onPageChange={() => {}} />);
    expect(screen.getByText("Loading your cases.")).toBeInTheDocument();

    rerender(<PortfolioSummary snapshot={{ ...samplePortfolio, total_cases: 0, total: 0, cases: [] }} loading={false} error={false} onRetry={onRetry} onPageChange={() => {}} />);
    expect(screen.getByText("You have no cases yet.")).toBeInTheDocument();

    rerender(<PortfolioSummary snapshot={null} loading={false} error onRetry={onRetry} onPageChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

describe("route map", () => {
  it("builds every link from kind and ids", () => {
    expect(referenceHref({ kind: "case", id: 7, case_id: null })).toBe("/cases/7");
    expect(referenceHref({ kind: "hearing", id: 1, case_id: 7 })).toBe("/cases/7");
    expect(referenceHref({ kind: "task", id: 1, case_id: null })).toBe("/calendar");
    expect(referenceHref({ kind: "event", id: 1, case_id: 9 })).toBe("/cases/9");
    expect(referenceHref({ kind: "document", id: 1, case_id: 9 })).toBe("/cases/9");
    expect(referenceHref({ kind: "fee", id: 1, case_id: 9 })).toBe("/billing");
    expect(entryHref({ kind: "event", id: 1, case_id: null })).toBe("/calendar");
  });
});
