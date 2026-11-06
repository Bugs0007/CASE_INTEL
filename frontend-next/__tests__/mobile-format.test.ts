import { describe, expect, it } from "vitest";
import { compactINR, dateTile, dueUrgency, dueWords, relativeDay } from "@/lib/mobile-format";

describe("dateTile", () => {
  it("splits a day into weekday, date and month", () => {
    expect(dateTile("2026-11-06")).toEqual({ weekday: "FRI", date: "6", month: "NOV" });
    expect(dateTile("2027-01-01")).toEqual({ weekday: "FRI", date: "1", month: "JAN" });
  });
});

describe("relativeDay", () => {
  const today = "2026-11-06";
  it("names the near days", () => {
    expect(relativeDay("2026-11-06", today)).toBe("Today");
    expect(relativeDay("2026-11-07", today)).toBe("Tomorrow");
    expect(relativeDay("2026-11-05", today)).toBe("Yesterday");
    expect(relativeDay("2026-11-11", today)).toBe("In 5 days");
    expect(relativeDay("2026-11-02", today)).toBe("4 days ago");
  });
  it("falls back to the date past two weeks", () => {
    expect(relativeDay("2026-12-25", today)).toBe("25 Dec");
    expect(relativeDay("2026-09-01", today)).toBe("1 Sep");
  });
});

describe("due dates", () => {
  const today = "2026-11-06";
  it("speaks louder the closer it is", () => {
    expect(dueUrgency("2026-11-04", today)).toBe("alert");
    expect(dueUrgency("2026-11-06", today)).toBe("pending");
    expect(dueUrgency("2026-11-08", today)).toBe("pending");
    expect(dueUrgency("2026-11-09", today)).toBe("none");
    expect(dueUrgency(null, today)).toBe("none");
  });
  it("words it", () => {
    expect(dueWords("2026-11-05", today)).toBe("1 day overdue");
    expect(dueWords("2026-11-03", today)).toBe("3 days overdue");
    expect(dueWords("2026-11-06", today)).toBe("Due today");
    expect(dueWords("2026-11-07", today)).toBe("Due tomorrow");
    expect(dueWords("2026-11-12", today)).toBe("Due in 6 days");
    expect(dueWords(null, today)).toBe("");
  });
});

describe("compactINR", () => {
  it("uses lakh and crore", () => {
    expect(compactINR("15000")).toBe("15K");
    expect(compactINR(240000)).toBe("2.4L");
    expect(compactINR(12000000)).toBe("1.2Cr");
    expect(compactINR("500")).toBe("500");
    expect(compactINR("x")).toBe("");
  });
});
