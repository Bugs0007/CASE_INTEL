import { describe, expect, it } from "vitest";
import { DEFAULT_FILTERS, activeFilterLabels, applyFilters } from "@/lib/advocate-search-results";
import type { AdvocateResultRow } from "@/types";

const row = (cnr: string, caseNumber: string, status = "Pending") =>
  ({ cnr_number: cnr, case_number: caseNumber, status, match_status: "check", petitioner: "A", respondent: "B" }) as AdvocateResultRow;

describe("activeFilterLabels", () => {
  it("says nothing when no filter is set", () => {
    expect(activeFilterLabels(DEFAULT_FILTERS)).toEqual([]);
  });

  it("names a one-year range the way a person would, so a stray 2026 to 2026 is visible", () => {
    expect(activeFilterLabels({ ...DEFAULT_FILTERS, yearFrom: 2026, yearTo: 2026 })).toEqual(["year 2026"]);
    expect(activeFilterLabels({ ...DEFAULT_FILTERS, yearFrom: 2019, yearTo: 2023 })).toEqual(["years 2019 to 2023"]);
    expect(activeFilterLabels({ ...DEFAULT_FILTERS, yearFrom: 2019 })).toEqual(["year 2019 or later"]);
    expect(activeFilterLabels({ ...DEFAULT_FILTERS, yearTo: 2019 })).toEqual(["year 2019 or earlier"]);
  });

  it("lists every narrowing filter and leaves the Show hidden switches out", () => {
    const labels = activeFilterLabels({
      ...DEFAULT_FILTERS,
      q: " rao ",
      status: "disposed",
      court: "Nirmal Court Complex",
      match: "verified",
      showExcluded: true,
      showOther: true,
    });
    expect(labels).toEqual(['search "rao"', "Disposed only", "court Nirmal Court Complex", "verified matches only"]);
  });
});

describe("the year filter against a result with older cases", () => {
  const rows = [row("1", "OS/740/2015"), row("2", "CC/312/2019"), row("3", "AS/55/2021")];

  it("hides every row filed outside the range, which is why 47 found can show an empty table", () => {
    expect(applyFilters(rows, { ...DEFAULT_FILTERS, yearFrom: 2026, yearTo: 2026 })).toEqual([]);
    expect(applyFilters(rows, DEFAULT_FILTERS)).toHaveLength(3);
  });
});
