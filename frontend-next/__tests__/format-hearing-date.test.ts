import { describe, it, expect } from "vitest";
import { formatHearingDate } from "@/lib/utils";

// Regression coverage for a live-verified bug: every Hearing.hearing_date
// is stored as midnight UTC (eCourts only ever provides a DATE, never a
// time), but the frontend was formatting it with a time component and
// converting to IST -- 00:00 UTC + 5:30 IST offset always renders as
// "5:30 AM", a fabricated clock time that looked like real data.
describe("formatHearingDate", () => {
  it("never renders a time component for a midnight-UTC hearing_date", () => {
    const result = formatHearingDate("2026-08-17T00:00:00Z");
    expect(result).not.toMatch(/\d{1,2}:\d{2}/);
    expect(result).not.toMatch(/AM|PM/i);
  });

  it("renders the date itself correctly", () => {
    expect(formatHearingDate("2026-08-17T00:00:00Z")).toBe("Aug 17, 2026");
  });

  it("stays date-only even for a non-midnight timestamp (no fabricated time slips through either way)", () => {
    const result = formatHearingDate("2026-08-17T14:45:00Z");
    expect(result).toBe("Aug 17, 2026");
    expect(result).not.toMatch(/\d{1,2}:\d{2}/);
  });

  it("returns an empty string for a missing date, same as formatDate", () => {
    expect(formatHearingDate(null)).toBe("");
    expect(formatHearingDate(undefined)).toBe("");
  });
});
