import { describe, it, expect } from "vitest";
import {
  agendaDays,
  buildCalendarItems,
  buildDayBuckets,
  dayMarkerCounts,
  formatEventTimes,
  hearingDayKey,
  plainDayKey,
} from "@/lib/calendar";
import type { CaseEvent, Hearing, Task } from "@/types";

// ---------------------------------------------------------------------------
// Fixtures: only the fields the calendar reads
// ---------------------------------------------------------------------------

function hearing(id: number, hearing_date: string, extra: Partial<Hearing> = {}): Hearing {
  return { id, case: 1, case_title: "Rao vs State", hearing_date, status: "scheduled", ...extra } as Hearing;
}

function task(id: number, due_date: string | null, extra: Partial<Task> = {}): Task {
  return {
    id,
    case: 1,
    title: `Task ${id}`,
    status: "pending",
    kind: "manual",
    due_date,
    ...extra,
  } as Task;
}

function event(id: number, date: string, extra: Partial<CaseEvent> = {}): CaseEvent {
  return {
    id,
    case: 1,
    title: `Event ${id}`,
    date,
    start_time: null,
    end_time: null,
    status: "scheduled",
    ...extra,
  } as CaseEvent;
}

// ---------------------------------------------------------------------------
// The India-date key for a hearing
// ---------------------------------------------------------------------------

describe("hearingDayKey", () => {
  it("keys an eCourts hearing (00:00 UTC) on the same India day", () => {
    // 00:00 UTC is 05:30 IST on the 6th.
    expect(hearingDayKey("2026-11-06T00:00:00Z")).toBe("2026-11-06");
    expect(hearingDayKey("2026-11-06T00:00:00+00:00")).toBe("2026-11-06");
  });

  it("flips to the next day at IST midnight, which is 18:30 UTC", () => {
    expect(hearingDayKey("2026-11-06T18:29:59Z")).toBe("2026-11-06");
    expect(hearingDayKey("2026-11-06T18:30:00Z")).toBe("2026-11-07");
  });

  it("puts a manual 00:30 IST hearing on its own India day, not the UTC one", () => {
    // 00:30 IST on the 7th is 19:00 UTC on the 6th.
    expect(hearingDayKey("2026-11-06T19:00:00Z")).toBe("2026-11-07");
    expect(hearingDayKey("2026-11-07T00:30:00+05:30")).toBe("2026-11-07");
  });

  it("keeps a 23:30 IST hearing on its own day", () => {
    expect(hearingDayKey("2026-11-06T23:30:00+05:30")).toBe("2026-11-06");
  });

  it("handles month and year boundaries", () => {
    expect(hearingDayKey("2026-12-31T20:00:00Z")).toBe("2027-01-01");
    expect(hearingDayKey("2026-02-28T19:00:00Z")).toBe("2026-03-01");
  });

  it("does not depend on the process timezone", () => {
    // The same instant must give the same key whatever TZ the runner has;
    // run the file under e.g. TZ=America/Los_Angeles to prove it.
    expect(hearingDayKey("2026-11-06T00:00:00Z")).toBe("2026-11-06");
  });

  it("falls back to the date part for something unparseable", () => {
    expect(hearingDayKey("not-a-date")).toBe("not-a-date".slice(0, 10));
  });
});

describe("plainDayKey", () => {
  it("keys task and event dates as-is", () => {
    expect(plainDayKey("2026-11-06")).toBe("2026-11-06");
    expect(plainDayKey("2026-11-06T00:00:00Z")).toBe("2026-11-06");
  });
});

// ---------------------------------------------------------------------------
// Merging hearings, tasks and events into day buckets
// ---------------------------------------------------------------------------

describe("buildDayBuckets", () => {
  const hearings = [hearing(1, "2026-11-06T00:00:00Z"), hearing(2, "2026-11-07T00:00:00Z")];
  const tasks = [task(10, "2026-11-06"), task(11, "2026-11-20")];
  const events = [event(20, "2026-11-06", { start_time: "15:00:00" }), event(21, "2026-11-08")];

  it("puts all three kinds on their own day", () => {
    const buckets = buildDayBuckets({ hearings, tasks, events });
    expect([...buckets.keys()].sort()).toEqual([
      "2026-11-06",
      "2026-11-07",
      "2026-11-08",
      "2026-11-20",
    ]);
    expect(buckets.get("2026-11-06")?.map((i) => i.key)).toEqual(["hearing-1", "event-20", "task-10"]);
    expect(buckets.get("2026-11-07")?.map((i) => i.key)).toEqual(["hearing-2"]);
    expect(buckets.get("2026-11-08")?.map((i) => i.key)).toEqual(["event-21"]);
    expect(buckets.get("2026-11-20")?.map((i) => i.key)).toEqual(["task-11"]);
  });

  it("keys a hearing by its India date but tasks and events as plain dates", () => {
    // A hearing at 00:30 IST on the 7th is the 6th in UTC -- it belongs on
    // the 7th, next to the task due that plain day.
    const buckets = buildDayBuckets({
      hearings: [hearing(1, "2026-11-06T19:00:00Z")],
      tasks: [task(10, "2026-11-07")],
      events: [event(20, "2026-11-07")],
    });
    expect([...buckets.keys()]).toEqual(["2026-11-07"]);
    expect(buckets.get("2026-11-07")).toHaveLength(3);
  });

  it("orders a day: hearings, then events (all-day first, then by start), then tasks", () => {
    const buckets = buildDayBuckets({
      hearings: [hearing(2, "2026-11-06T00:00:00Z"), hearing(1, "2026-11-06T00:00:00Z")],
      tasks: [task(31, "2026-11-06"), task(30, "2026-11-06")],
      events: [
        event(42, "2026-11-06", { start_time: "16:00:00" }),
        event(41, "2026-11-06", { start_time: "09:30:00" }),
        event(40, "2026-11-06", { start_time: null }),
      ],
    });
    expect(buckets.get("2026-11-06")?.map((i) => i.key)).toEqual([
      "hearing-1",
      "hearing-2",
      "event-40",
      "event-41",
      "event-42",
      "task-30",
      "task-31",
    ]);
  });

  it("drops tasks with no due date and dismissed tasks, keeps completed ones", () => {
    const items = buildCalendarItems({
      tasks: [
        task(1, null),
        task(2, "2026-11-06", { status: "cancelled" }),
        task(3, "2026-11-06", { status: "completed" }),
        task(4, "2026-11-06", { status: "in_progress" }),
      ],
    });
    expect(items.map((i) => i.key)).toEqual(["task-3", "task-4"]);
  });

  it("includes only the kinds asked for", () => {
    const only = (kinds: ("hearing" | "task" | "event")[]) =>
      buildCalendarItems({ hearings, tasks, events, kinds: new Set(kinds) }).map((i) => i.kind);
    expect(new Set(only(["hearing"]))).toEqual(new Set(["hearing"]));
    expect(new Set(only(["task", "event"]))).toEqual(new Set(["task", "event"]));
    expect(only([])).toEqual([]);
  });

  it("treats a missing source as empty", () => {
    expect(buildDayBuckets({}).size).toBe(0);
    expect(buildDayBuckets({ hearings }).size).toBe(2);
  });

  it("is not affected by an order-direction task's source order", () => {
    const direction = task(5, "2026-11-06", {
      kind: "order_direction",
      source_order: 77,
      needs_review: true,
      due_date_basis: "relative_to_order",
      due_date_basis_display: "Counted from the order date",
    });
    const [item] = buildCalendarItems({ tasks: [direction] });
    expect(item.kind === "task" && item.task.source_order).toBe(77);
  });
});

describe("dayMarkerCounts", () => {
  it("counts hearings always, tasks only while open, events unless cancelled", () => {
    const items = buildCalendarItems({
      hearings: [hearing(1, "2026-11-06T00:00:00Z", { status: "cancelled" })],
      tasks: [task(1, "2026-11-06"), task(2, "2026-11-06", { status: "completed" })],
      events: [
        event(1, "2026-11-06"),
        event(2, "2026-11-06", { status: "cancelled" }),
        event(3, "2026-11-06", { status: "completed" }),
      ],
    });
    expect(dayMarkerCounts(items)).toEqual({ hearing: 1, task: 1, event: 2 });
    expect(dayMarkerCounts(undefined)).toEqual({ hearing: 0, task: 0, event: 0 });
  });
});

describe("agendaDays", () => {
  const buckets = buildDayBuckets({
    hearings: [hearing(1, "2026-11-04T00:00:00Z"), hearing(2, "2026-12-04T00:00:00Z")],
    tasks: [task(1, "2026-11-10"), task(2, "2026-11-03")],
    events: [event(1, "2026-11-10"), event(2, "2026-12-03")],
  });

  it("lists only days with something on them, from the start day, in order", () => {
    const days = agendaDays(buckets, "2026-11-04", 30);
    // The overdue task on 2026-11-03 is before the window and left out.
    expect(days.map((d) => d.day)).toEqual(["2026-11-04", "2026-11-10", "2026-12-03"]);
    expect(days[1].items.map((i) => i.key)).toEqual(["event-1", "task-1"]);
  });

  it("covers exactly `days` days, counting the start day", () => {
    // 2026-11-04 + 29 = 2026-12-03 (included); 2026-12-04 is the 31st day.
    const days = agendaDays(buckets, "2026-11-04", 30).map((d) => d.day);
    expect(days).toContain("2026-12-03");
    expect(days).not.toContain("2026-12-04");
    expect(agendaDays(buckets, "2026-11-05", 30).map((d) => d.day)).toEqual([
      "2026-11-10",
      "2026-12-03",
      "2026-12-04",
    ]);
  });

  it("is empty when nothing falls in the window", () => {
    expect(agendaDays(buckets, "2027-03-01", 30)).toEqual([]);
  });
});

describe("formatEventTimes", () => {
  it("says all-day, a start, or a range", () => {
    expect(formatEventTimes(null, null)).toBe("All day");
    expect(formatEventTimes("10:30:00", null)).toBe("10:30 AM");
    expect(formatEventTimes("10:30:00", "12:00:00")).toBe("10:30 AM – 12:00 PM");
    expect(formatEventTimes("15:05:00", "16:45:00")).toBe("3:05 PM – 4:45 PM");
  });
});
