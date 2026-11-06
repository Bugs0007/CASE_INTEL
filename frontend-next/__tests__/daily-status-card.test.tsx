import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api/client", () => ({
  apiClient: vi.fn(async (path: string) => {
    if (path === "/cases/7/daily-status/") return ENTRIES;
    throw new Error("unexpected " + path);
  }),
}));

import {
  DailyStatusCard,
  DailyStatusView,
  purposeTone,
  relativeDayLabel,
} from "@/components/cases/daily-status-card";
import type { DailyStatusEntry } from "@/types/daily-status";

const LONG =
  "Petitioner counsel present. Respondent counsel absent. Memo filed by the petitioner counsel " +
  "stay is granted. Hence call on 19.11.2026 for filing of counter and further proceedings.";

const ENTRIES: DailyStatusEntry[] = [
  {
    business_date: "2026-11-05",
    court_name: "Principal Junior Civil Judge, Sangareddy",
    business_text: LONG,
    next_purpose: "STAY",
    next_hearing_date: "2026-11-19",
    fetched_at: "2026-11-06T04:00:00Z",
  },
  {
    business_date: "2026-10-20",
    court_name: "Principal Junior Civil Judge, Sangareddy",
    business_text: "Counsel sought time.",
    next_purpose: "STAY",
    next_hearing_date: "2026-11-05",
    fetched_at: "2026-11-06T04:00:00Z",
  },
  {
    business_date: "2026-10-01",
    court_name: "",
    business_text: "",
    next_purpose: "",
    next_hearing_date: null,
    fetched_at: "2026-11-06T04:00:00Z",
  },
];

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 6, 10, 0, 0)); // 6 Nov 2026, local time
});

afterEach(() => {
  vi.useRealTimers();
});

describe("DailyStatusView", () => {
  it("shows the latest hearing with date chip, purpose pill and days until next", () => {
    render(<DailyStatusView entries={ENTRIES} />);
    expect(screen.getByRole("article", { name: "Hearing on 5 Nov 2026" })).toBeInTheDocument();
    expect(screen.getByText("Principal Junior Civil Judge, Sangareddy")).toBeInTheDocument();
    expect(screen.getAllByText("STAY")[0]).toBeInTheDocument();
    expect(screen.getByText("19 Nov 2026")).toBeInTheDocument();
    expect(screen.getByText(/In 13 days/)).toBeInTheDocument();
  });

  it("clamps long business text behind Read more", () => {
    render(<DailyStatusView entries={ENTRIES} />);
    const text = screen.getByText(LONG);
    expect(text.className).toContain("line-clamp-3");
    fireEvent.click(screen.getByRole("button", { name: "Read more" }));
    expect(text.className).not.toContain("line-clamp-3");
    expect(screen.getByRole("button", { name: "Show less" })).toBeInTheDocument();
  });

  it("keeps earlier hearings folded until asked", () => {
    render(<DailyStatusView entries={ENTRIES} />);
    expect(screen.queryByText("Counsel sought time.")).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /Earlier hearings/ });
    expect(toggle).toHaveTextContent("(2)");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Counsel sought time.")).toBeInTheDocument();
    expect(screen.getByText("The court recorded no business for this date.")).toBeInTheDocument();
  });

  it("honours reduced motion on animated parts", () => {
    render(<DailyStatusView entries={ENTRIES} />);
    expect(screen.getByRole("article").className).toContain("motion-reduce:animate-none");
  });

  it("has plain-language empty, loading and error states", () => {
    const { rerender } = render(<DailyStatusView entries={[]} />);
    expect(screen.getByText(/Nothing recorded yet/)).toBeInTheDocument();

    rerender(<DailyStatusView entries={undefined} isLoading />);
    expect(screen.getByRole("status", { name: "Loading daily status" })).toBeInTheDocument();

    const onRetry = vi.fn();
    rerender(<DailyStatusView entries={undefined} isError onRetry={onRetry} />);
    expect(screen.getByText(/couldn.t load what the court recorded/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});

describe("helpers", () => {
  it("labels days relative to today", () => {
    expect(relativeDayLabel("2026-11-06")).toBe("Today");
    expect(relativeDayLabel("2026-11-07")).toBe("Tomorrow");
    expect(relativeDayLabel("2026-11-05")).toBe("Yesterday");
    expect(relativeDayLabel("2026-11-01")).toBe("5 days ago");
    expect(relativeDayLabel("2026-11-19")).toBe("In 13 days");
  });

  it("colours purposes by kind", () => {
    expect(purposeTone("STAY")).toContain("amber");
    expect(purposeTone("For Judgment")).toContain("violet");
    expect(purposeTone("EVIDENCE")).toContain("sky");
    expect(purposeTone("Misc")).toContain("slate");
  });
});

describe("DailyStatusCard", () => {
  it("loads the case's entries from the API", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <DailyStatusCard caseId={7} />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("article", { name: "Hearing on 5 Nov 2026" })).toBeInTheDocument();
  });
});
