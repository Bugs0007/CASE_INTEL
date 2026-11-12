import { describe, expect, it } from "vitest";
import { buildChooserSections, type ChooserCase } from "@/lib/assistant";

const c = (id: number, title: string, case_number: string, next_hearing_date: string | null = null) =>
  ({ id, title, case_number, next_hearing_date }) as ChooserCase;

describe("case chooser while searching", () => {
  it("lists each match once, recent first", () => {
    const cases = [c(1, "Zed vs Bank", "WP/2010/2025", "2026-11-13"), c(2, "Abel vs State", "WP/2011/2025")];
    const sections = buildChooserSections({
      cases,
      filter: "WP/201",
      pageCaseId: null,
      recentCaseIds: [1],
      today: "2026-11-12",
      soonUntil: "2026-11-19",
    });
    expect(sections).toHaveLength(1);
    expect(sections[0].cases.map((item) => item.id)).toEqual([1, 2]);
  });
});
