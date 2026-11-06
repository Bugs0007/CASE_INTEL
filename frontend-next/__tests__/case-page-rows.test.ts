import { describe, expect, it } from "vitest";
import { pageBudget } from "@/lib/case-page-budget";
import {
  agoShort,
  allHearingRows,
  caseFacts,
  comingUpRows,
  compactHearingRows,
  filterHearingRows,
  miniMonthWeeks,
  syncState,
  weekStrip,
} from "@/lib/case-page-rows";
import { buildDayBuckets } from "@/lib/calendar";
import { caseDetail, hearings, orders } from "../e2e/fixtures";
import type { Case, CourtOrder, Hearing } from "@/types";

// Thursday 5 November 2026.
const TODAY = "2026-11-05";
const H = (id: number, date: string, status: string, extra: Partial<Hearing> = {}) =>
  ({ ...hearings[0], id, hearing_date: `${date}T00:00:00Z`, status, ...extra }) as unknown as Hearing;
const order = (date: string, hasFile = true) =>
  ({ ...orders[0], id: Math.floor(Math.random() * 1e6), order_date: date, has_file: hasFile }) as unknown as CourtOrder;

describe("the row budget by window", () => {
  it("881px tall and up: five hearings, five documents, a month, three events, client updates", () => {
    for (const height of [881, 960, 1080, 1400]) {
      expect(pageBudget(1920, height)).toMatchObject({
        fit: true,
        hearingRows: 5,
        documentRows: 5,
        documentRowsWithCheck: 4,
        calendar: "month",
        calendarItems: 3,
        showClientUpdates: true,
      });
    }
  });

  it("801 to 880px: four of each, a month, three events, no client updates", () => {
    for (const height of [801, 864, 880]) {
      expect(pageBudget(1536, height)).toMatchObject({
        fit: true,
        hearingRows: 4,
        documentRows: 4,
        documentRowsWithCheck: 4,
        calendar: "month",
        calendarItems: 3,
        showClientUpdates: false,
      });
    }
  });

  it("800px and under: three of each, a week strip, two events, no client updates", () => {
    for (const height of [700, 760, 800]) {
      expect(pageBudget(1280, height)).toMatchObject({
        fit: true,
        hearingRows: 3,
        documentRows: 3,
        documentRowsWithCheck: 2,
        calendar: "week",
        calendarItems: 2,
        showClientUpdates: false,
      });
    }
  });

  it("below 1024px wide or under 700px tall the page stops trying to fit", () => {
    expect(pageBudget(1023, 900).fit).toBe(false);
    expect(pageBudget(1600, 699).fit).toBe(false);
    expect(pageBudget(1024, 700).fit).toBe(true);
  });

  it("the rail is 352px from 1400 wide and 320px under it", () => {
    expect(pageBudget(1400, 900).railWidth).toBe(352);
    expect(pageBudget(1399, 900).railWidth).toBe(320);
    expect(pageBudget(1920, 960).railWidth).toBe(352);
    expect(pageBudget(1280, 760).railWidth).toBe(320);
  });
});

describe("hearing rows", () => {
  const seven = [
    H(1, "2026-11-19", "scheduled", { cause_list_status: "not_published" }),
    H(2, "2026-02-10", "scheduled"),
    H(3, "2026-01-20", "completed", { outcome: "Interim direction" }),
    H(4, "2026-01-12", "completed"),
    H(5, "2026-01-05", "completed"),
    H(6, "2025-12-18", "completed"),
    H(7, "2025-11-20", "completed"),
  ];

  it("renders exactly as many rows as asked for, not all of them", () => {
    expect(compactHearingRows(seven, [], TODAY, 5).rows).toHaveLength(5);
    expect(compactHearingRows(seven, [], TODAY, 4).rows).toHaveLength(4);
    expect(compactHearingRows(seven, [], TODAY, 3).rows).toHaveLength(3);
    expect(compactHearingRows(seven, [], TODAY, 3).total).toBe(7);
    expect(compactHearingRows(seven.slice(0, 2), [], TODAY, 5).rows).toHaveLength(2);
  });

  it("the next hearing is first and highlighted; then the most recent", () => {
    const { rows } = compactHearingRows(seven, [], TODAY, 4);
    expect(rows.map((r) => r.hearing.id)).toEqual([1, 2, 3, 4]);
    expect(rows[0]).toMatchObject({ isNext: true, tone: "upcoming", status: "UPCOMING", text: "Cause list not published yet" });
    expect(rows.slice(1).every((r) => !r.isNext)).toBe(true);
  });

  it("a scheduled hearing whose date has passed reads AWAITING UPDATE, never UPCOMING", () => {
    const row = allHearingRows(seven, [], TODAY).find((r) => r.hearing.id === 2);
    expect(row).toMatchObject({ status: "AWAITING UPDATE", tone: "other" });
  });

  it("a passed hearing with an order on its date says ORDER PASSED and carries the order", () => {
    const o = order("2026-01-20");
    const row = allHearingRows(seven, [o], TODAY).find((r) => r.hearing.id === 3);
    expect(row).toMatchObject({ status: "ORDER PASSED", tone: "order" });
    expect(row?.order?.id).toBe(o.id);
    expect(allHearingRows(seven, [o], TODAY).find((r) => r.hearing.id === 4)?.order).toBeNull();
  });

  it("filters: upcoming, passed, orders", () => {
    const rows = allHearingRows(seven, [order("2026-01-20"), order("2025-11-20")], TODAY);
    expect(filterHearingRows(rows, "all")).toHaveLength(7);
    expect(filterHearingRows(rows, "upcoming")).toHaveLength(1);
    expect(filterHearingRows(rows, "passed")).toHaveLength(6);
    expect(filterHearingRows(rows, "orders")).toHaveLength(2);
  });
});

describe("calendar", () => {
  it("the mini month is five rows of seven and always contains today", () => {
    for (const today of ["2026-11-05", "2026-08-31", "2026-05-30", "2026-02-01", "2026-10-31"]) {
      const weeks = miniMonthWeeks(today);
      expect(weeks).toHaveLength(5);
      weeks.forEach((w) => expect(w).toHaveLength(7));
      expect(weeks.flat().filter((d) => d.isToday)).toHaveLength(1);
    }
  });

  it("November 2026 starts on Sunday 1 and ends with the next month's days", () => {
    const weeks = miniMonthWeeks(TODAY);
    expect(weeks[0]?.[0]?.day).toBe("2026-11-01");
    expect(weeks[4]?.[6]?.day).toBe("2026-12-05");
    expect(weeks[4]?.[6]?.inMonth).toBe(false);
  });

  it("the week strip is Monday to Sunday around today", () => {
    const week = weekStrip(TODAY);
    expect(week.map((d) => d.day)).toEqual([
      "2026-11-02",
      "2026-11-03",
      "2026-11-04",
      "2026-11-05",
      "2026-11-06",
      "2026-11-07",
      "2026-11-08",
    ]);
    expect(week.find((d) => d.isToday)?.day).toBe(TODAY);
  });

  it("coming up lists the next hearings, events and deadlines, capped at the budget", () => {
    const buckets = buildDayBuckets({
      hearings: [H(1, "2026-11-19", "scheduled", { location: "High Court" }), H(2, "2026-10-01", "completed")],
      events: [{ id: 1, case: 1, title: "Client call", date: "2026-11-12", start_time: null, end_time: null, status: "scheduled" }] as never,
      tasks: [{ id: 1, title: "File rejoinder", due_date: "2026-11-23", status: "pending", kind: "manual" }] as never,
    });
    expect(comingUpRows(buckets, TODAY, 3).map((r) => [r.day, r.text])).toEqual([
      ["2026-11-12", "Client call"],
      ["2026-11-19", "Hearing · High Court"],
      ["2026-11-23", "Task · File rejoinder"],
    ]);
    expect(comingUpRows(buckets, TODAY, 2)).toHaveLength(2);
  });
});

describe("header and facts", () => {
  it("says how long ago tracking synced, in short form", () => {
    const now = new Date("2026-11-05T12:00:00Z").getTime();
    expect(agoShort("2026-11-05T11:59:40Z", now)).toBe("just now");
    expect(agoShort("2026-11-05T11:55:00Z", now)).toBe("5m ago");
    expect(agoShort("2026-11-05T10:00:00Z", now)).toBe("2h ago");
    expect(agoShort("2026-11-02T12:00:00Z", now)).toBe("3d ago");
  });

  it("the sync status and its dot", () => {
    const now = new Date("2026-11-05T12:00:00Z").getTime();
    const base = { tracking_enabled: true, fetch_status: "success", last_fetched_at: "2026-11-05T10:00:00Z", tracking_freshness: undefined } as never;
    expect(syncState(base, now)).toEqual({ label: "Court tracking synced 2h ago", tone: "ok" });
    expect(syncState({ ...(base as object), tracking_freshness: { stale: true } } as never, now).tone).toBe("stale");
    expect(syncState({ ...(base as object), fetch_status: "failed" } as never, now)).toEqual({ label: "Court tracking failed", tone: "failed" });
    expect(syncState({ ...(base as object), tracking_enabled: false } as never, now).tone).toBe("off");
    expect(syncState({ ...(base as object), last_fetched_at: null } as never, now).label).toBe("Court tracking not synced yet");
  });

  it("the six facts", () => {
    const facts = caseFacts(caseDetail as unknown as Case);
    expect(facts).toEqual({
      court: "Telangana High Court",
      stage: "Interim order passed",
      side: "",
      client: "Butham Srinivas",
      filed: "2026-08-14",
      cnr: "HBHC010234562026",
    });
    expect(caseFacts({ ...(caseDetail as object), user_party_role: "respondent" } as unknown as Case).side).toBe("Respondent");
  });
});
