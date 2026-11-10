import { describe, it, expect } from "vitest";
import {
  NO_CLIENT_LABEL,
  NO_COURT_LABEL,
  groupCases,
  parseGrouping,
} from "@/lib/case-grouping";
import type { Case } from "@/types";

// The pure grouping rules behind "Group by court / client" on the Cases page.
// Only the fields grouping reads are set; the rest is cast away.
const TODAY = "2026-11-06";

let nextId = 1;
function c(fields: Partial<Case>): Case {
  return { id: nextId++, client_name: "", client_detail: null, court_name: null, next_hearing_date: null, ...fields } as Case;
}
const client = (id: number, name: string) => ({ id, name, client_type: "individual" as const });
const labels = (cases: Case[], grouping: "court" | "client") => groupCases(cases, grouping, TODAY).map((g) => g.label);

describe("parseGrouping", () => {
  it("accepts the three choices and nothing else", () => {
    expect(parseGrouping("none")).toBe("none");
    expect(parseGrouping("court")).toBe("court");
    expect(parseGrouping("client")).toBe("client");
    expect(parseGrouping("Court")).toBeNull();
    expect(parseGrouping("judge")).toBeNull();
    expect(parseGrouping("")).toBeNull();
    expect(parseGrouping(null)).toBeNull();
    expect(parseGrouping(undefined)).toBeNull();
  });
});

describe("groupCases", () => {
  it("returns no groups when not grouping", () => {
    expect(groupCases([c({ court_name: "A" })], "none", TODAY)).toEqual([]);
  });

  describe("by court", () => {
    it("treats spellings that differ in case or spacing as one court", () => {
      const groups = groupCases(
        [
          c({ court_name: "Telangana High Court" }),
          c({ court_name: "  telangana   high court " }),
          c({ court_name: "TELANGANA HIGH COURT" }),
          c({ court_name: "Family Court, Secunderabad" }),
        ],
        "court",
        TODAY,
      );
      expect(groups.map((g) => [g.key, g.cases.length]).sort()).toEqual([
        ["n:family court, secunderabad", 1],
        ["n:telangana high court", 3],
      ]);
    });

    it("shows the spelling most of the group's cases use, tidied", () => {
      const groups = groupCases(
        [
          c({ court_name: "telangana high court" }),
          c({ court_name: " Telangana  High Court " }),
          c({ court_name: "Telangana High Court" }),
        ],
        "court",
        TODAY,
      );
      expect(groups).toHaveLength(1);
      // Two of the three cases spell it this way once the spaces are tidied.
      expect(groups[0].label).toBe("Telangana High Court");
    });

    it("on an even split shows the spelling the list met first", () => {
      expect(labels([c({ court_name: "telangana high court" }), c({ court_name: "Telangana High Court" })], "court")).toEqual([
        "telangana high court",
      ]);
      expect(labels([c({ court_name: "Telangana High Court" }), c({ court_name: "telangana high court" })], "court")).toEqual([
        "Telangana High Court",
      ]);
    });

    it("puts cases with no court (null, empty, blank, or absent) in one last group", () => {
      const noName = { ...c({}), court_name: undefined } as Case;
      const groups = groupCases(
        [
          c({ court_name: null, next_hearing_date: "2026-11-06T00:00:00Z" }), // soonest hearing of all
          c({ court_name: "" }),
          c({ court_name: "   " }),
          noName,
          c({ court_name: "Sessions Court", next_hearing_date: "2026-12-01T00:00:00Z" }),
        ],
        "court",
        TODAY,
      );
      expect(groups.map((g) => g.label)).toEqual(["Sessions Court", NO_COURT_LABEL]);
      expect(groups[1].missing).toBe(true);
      expect(groups[1].cases).toHaveLength(4);
      expect(groups[0].missing).toBe(false);
    });

    it("keeps cases in the order they came in within a group", () => {
      const a = c({ court_name: "X" });
      const b = c({ court_name: "Y" });
      const d = c({ court_name: "X" });
      const e = c({ court_name: "X" });
      const groups = groupCases([a, b, d, e], "court", TODAY);
      expect(groups.find((g) => g.label === "X")!.cases).toEqual([a, d, e]);
    });
  });

  describe("by client", () => {
    it("groups on the linked client's id, so two names for one client are one group", () => {
      const groups = groupCases(
        [
          c({ client_detail: client(7, "Meera Nair"), client_name: "Meera Nair" }),
          c({ client_detail: client(7, "Meera Nair"), client_name: "M. Nair (typed)" }),
        ],
        "client",
        TODAY,
      );
      expect(groups).toHaveLength(1);
      expect(groups[0].label).toBe("Meera Nair");
      expect(groups[0].key).toBe("i:7");
    });

    it("keeps two different clients with the same name apart", () => {
      const groups = groupCases(
        [c({ client_detail: client(1, "Ramesh Kumar") }), c({ client_detail: client(2, "Ramesh Kumar") })],
        "client",
        TODAY,
      );
      expect(groups).toHaveLength(2);
      expect(groups.map((g) => g.key).sort()).toEqual(["i:1", "i:2"]);
    });

    it("falls back to the typed client name, compared like a court name", () => {
      const groups = groupCases(
        [c({ client_name: "Rao & Sons Builders" }), c({ client_name: " rao &  sons builders" }), c({ client_name: "Anand Textiles" })],
        "client",
        TODAY,
      );
      expect(groups.map((g) => [g.label, g.cases.length]).sort()).toEqual([
        ["Anand Textiles", 1],
        ["Rao & Sons Builders", 2],
      ]);
    });

    it("does not merge a name-only case into a linked client of the same name", () => {
      const groups = groupCases(
        [c({ client_detail: client(3, "Kavitha Reddy") }), c({ client_name: "Kavitha Reddy" })],
        "client",
        TODAY,
      );
      expect(groups).toHaveLength(2);
    });

    it("puts cases with no client in one last group", () => {
      const groups = groupCases(
        [c({ client_name: "" }), c({ client_name: "  " }), c({ client_detail: client(1, "Zed"), next_hearing_date: "2027-01-01T00:00:00Z" })],
        "client",
        TODAY,
      );
      expect(groups.map((g) => g.label)).toEqual(["Zed", NO_CLIENT_LABEL]);
      expect(groups[1].cases).toHaveLength(2);
    });
  });

  describe("order and next hearing", () => {
    it("orders groups by their soonest upcoming hearing, groups with none last, ties by name", () => {
      const groups = groupCases(
        [
          c({ court_name: "Zeta Court", next_hearing_date: "2026-11-20T00:00:00Z" }),
          c({ court_name: "Zeta Court", next_hearing_date: "2026-11-09T00:00:00Z" }), // makes Zeta the soonest
          c({ court_name: "Beta Court", next_hearing_date: "2026-11-12T00:00:00Z" }),
          c({ court_name: "Alpha Court", next_hearing_date: "2026-11-12T00:00:00Z" }), // ties Beta -> by name
          c({ court_name: "Nothing Court" }),
          c({ court_name: "Also Nothing Court" }),
        ],
        "court",
        TODAY,
      );
      expect(groups.map((g) => g.label)).toEqual(["Zeta Court", "Alpha Court", "Beta Court", "Also Nothing Court", "Nothing Court"]);
      expect(groups[0].nextHearingDay).toBe("2026-11-09");
      expect(groups[3].nextHearingDay).toBeNull();
    });

    it("ignores hearings that are already past when ordering and labelling", () => {
      const groups = groupCases(
        [
          c({ court_name: "Old Court", next_hearing_date: "2026-10-01T00:00:00Z" }),
          c({ court_name: "New Court", next_hearing_date: "2026-12-01T00:00:00Z" }),
        ],
        "court",
        TODAY,
      );
      expect(groups.map((g) => g.label)).toEqual(["New Court", "Old Court"]);
      expect(groups[1].nextHearingDay).toBeNull();
    });

    it("reads a hearing's day in India: 00:30 IST on the 6th is the 6th, 23:30 IST on the 5th is past", () => {
      // 2026-11-05T19:00:00Z is 00:30 IST on the 6th -- today, so upcoming.
      const today = groupCases([c({ court_name: "A", next_hearing_date: "2026-11-05T19:00:00Z" })], "court", TODAY);
      expect(today[0].nextHearingDay).toBe("2026-11-06");
      // 2026-11-05T18:00:00Z is 23:30 IST on the 5th -- yesterday, so past.
      const past = groupCases([c({ court_name: "A", next_hearing_date: "2026-11-05T18:00:00Z" })], "court", TODAY);
      expect(past[0].nextHearingDay).toBeNull();
    });

    it("counts a hearing today as upcoming", () => {
      const groups = groupCases([c({ court_name: "A", next_hearing_date: "2026-11-06T00:00:00Z" })], "court", TODAY);
      expect(groups[0].nextHearingDay).toBe("2026-11-06");
    });
  });
});
