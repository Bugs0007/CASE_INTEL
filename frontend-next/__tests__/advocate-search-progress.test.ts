import { describe, expect, it } from "vitest";
import { LONG_WAIT_MS, describeSearchProgress, formatElapsed } from "@/lib/advocate-search-progress";

const T0 = Date.parse("2026-11-05T10:00:00Z");

function job(overrides: Record<string, unknown> = {}) {
  return {
    status: "running" as const,
    created_at: new Date(T0 - 5_000).toISOString(),
    started_at: new Date(T0).toISOString(),
    progress_current: 2,
    progress_total: 10,
    complexes_done: 7,
    complexes_total_known: 18,
    current_district: "Karimnagar",
    ...overrides,
  };
}

describe("formatElapsed", () => {
  it.each([
    [0, "0s"],
    [42_000, "42s"],
    [252_000, "4m 12s"],
    [3_900_000, "1h 05m"],
    [-5_000, "0s"],
  ])("%i ms is %s", (ms, text) => {
    expect(formatElapsed(ms)).toBe(text);
  });
});

describe("describeSearchProgress", () => {
  it("running: counts, the district, and how long it has been going", () => {
    const text = describeSearchProgress(job(), T0 + 252_000);
    expect(text.counts).toBe("7 of 18 court complexes searched · 7 more districts still to be listed");
    expect(text.district).toBe("Now searching Karimnagar");
    expect(text.elapsed).toBe("Elapsed 4m 12s");
    expect(text.waiting).toBeNull();
  });

  it("does not claim more districts are coming once the last one is listed", () => {
    const text = describeSearchProgress(job({ progress_current: 9, progress_total: 10 }), T0 + 1000);
    expect(text.counts).toBe("7 of 18 court complexes searched");
  });

  it("says one more district in the singular", () => {
    const text = describeSearchProgress(job({ progress_current: 8, progress_total: 10 }), T0 + 1000);
    expect(text.counts).toContain("1 more district still to be listed");
  });

  it("before any district is listed there is nothing to count yet", () => {
    const text = describeSearchProgress(job({ complexes_total_known: 0, complexes_done: 0, current_district: "" }), T0 + 1000);
    expect(text.counts).toBe("Listing the court complexes…");
    expect(text.district).toBeNull();
  });

  it("an older job without the counters still reads sensibly", () => {
    const text = describeSearchProgress(job({ complexes_total_known: null, complexes_done: null, current_district: "" }), T0);
    expect(text.counts).toBe("Listing the court complexes…");
  });

  it("queued: a plain waiting message, not a count", () => {
    const text = describeSearchProgress(job({ status: "queued", started_at: null }), T0 + 10_000);
    expect(text.waiting).toMatch(/^Waiting for the background worker to start this search\./);
    expect(text.waiting).not.toMatch(/Still waiting/);
    expect(text.counts).toBeNull();
    expect(text.elapsed).toBeNull();
  });

  it("queued for a long time: says so, with how long", () => {
    const text = describeSearchProgress(
      job({ status: "queued", started_at: null }),
      T0 - 5_000 + LONG_WAIT_MS + 30_000,
    );
    expect(text.waiting).toContain("Still waiting after 1m 30s");
  });

  it("finished or failed jobs have no progress text", () => {
    for (const status of ["succeeded", "failed", "cancelled"] as const) {
      expect(describeSearchProgress(job({ status }), T0)).toEqual({
        waiting: null,
        counts: null,
        district: null,
        elapsed: null,
      });
    }
  });
});
