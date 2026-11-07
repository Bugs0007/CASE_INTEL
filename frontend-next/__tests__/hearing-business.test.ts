import { describe, expect, it } from "vitest";
import {
  businessForHearing,
  checkErrorNote,
  hearingBusinessInfo,
  indexBusinessByDate,
  listedBusinessDays,
  oneLine,
  type HearingBusinessInputs,
} from "@/lib/hearing-business";
import { APIError } from "@/lib/api/client";
import type { DailyStatusEntry } from "@/types/daily-status";
import type { Hearing } from "@/types";

const entry = (business_date: string, extra: Partial<DailyStatusEntry> = {}): DailyStatusEntry => ({
  business_date,
  court_name: "Principal Junior Civil Judge",
  business_text: `Business on ${business_date}`,
  next_purpose: "STAY",
  next_hearing_date: null,
  fetched_at: "2026-11-06T04:00:00Z",
  ...extra,
});

const hearing = (hearing_date: string, extra: Partial<Hearing> = {}): Hearing =>
  ({ id: 1, hearing_date, status: "completed", business_date: null, ...extra }) as Hearing;

const TODAY = "2026-11-07";

function inputs(over: Partial<HearingBusinessInputs> = {}): HearingBusinessInputs {
  return {
    enabled: true,
    status: "ready",
    index: indexBusinessByDate([entry("2026-11-01")]),
    listed: new Set(["2026-11-01", "2026-10-20"]),
    today: TODAY,
    ...over,
  };
}

describe("indexBusinessByDate / businessForHearing", () => {
  it("maps entries by their plain date and gives undefined for a hearing with none", () => {
    const index = indexBusinessByDate([entry("2026-11-05"), entry("2026-10-20")]);
    expect([...index.keys()].sort()).toEqual(["2026-10-20", "2026-11-05"]);
    expect(businessForHearing(index, hearing("2026-11-05T00:00:00Z"))?.business_text).toBe("Business on 2026-11-05");
    expect(businessForHearing(index, hearing("2026-11-06T00:00:00Z"))).toBeUndefined();
  });

  it("matches on the hearing's India day, not its UTC day", () => {
    const index = indexBusinessByDate([entry("2026-11-06")]);
    // 00:00 UTC on the 6th is 05:30 IST on the 6th.
    expect(businessForHearing(index, hearing("2026-11-06T00:00:00Z"))).toBeDefined();
    // 19:00 UTC on the 5th is 00:30 IST on the 6th: still the 6th in India.
    expect(businessForHearing(index, hearing("2026-11-05T19:00:00Z"))).toBeDefined();
    // 19:00 UTC on the 6th is the 7th in India: not the 6th's business.
    expect(businessForHearing(index, hearing("2026-11-06T19:00:00Z"))).toBeUndefined();
  });

  it("keeps the first entry when a date somehow has two, and copes with no data", () => {
    const index = indexBusinessByDate([entry("2026-11-05", { business_text: "first" }), entry("2026-11-05", { business_text: "second" })]);
    expect(index.get("2026-11-05")?.business_text).toBe("first");
    expect(indexBusinessByDate(undefined).size).toBe(0);
  });
});

describe("listedBusinessDays", () => {
  it("collects the business dates the court's history links", () => {
    const days = listedBusinessDays([
      hearing("2026-11-19T00:00:00Z", { business_date: "2026-11-05" }),
      hearing("2026-11-05T00:00:00Z", { business_date: "2026-10-20" }),
      hearing("2026-10-20T00:00:00Z", { business_date: null }),
    ]);
    expect([...days].sort()).toEqual(["2026-10-20", "2026-11-05"]);
  });
});

describe("hearingBusinessInfo", () => {
  it("is off for a case that is not a district case", () => {
    expect(hearingBusinessInfo(hearing("2026-11-01T00:00:00Z"), inputs({ enabled: false }))).toEqual({ kind: "off" });
  });

  it("returns the saved entry for a hearing on its day", () => {
    const info = hearingBusinessInfo(hearing("2026-11-01T00:00:00Z"), inputs());
    expect(info.kind).toBe("entry");
  });

  it("says missing for a passed hearing whose business is listed but not saved", () => {
    expect(hearingBusinessInfo(hearing("2026-10-20T00:00:00Z"), inputs())).toEqual({ kind: "missing" });
  });

  it("says unlisted for a passed hearing the court links no business for", () => {
    expect(hearingBusinessInfo(hearing("2026-09-01T00:00:00Z"), inputs())).toEqual({ kind: "unlisted" });
  });

  it("says nothing for a hearing ahead, one today without an entry, or a cancelled one", () => {
    expect(hearingBusinessInfo(hearing("2026-11-19T00:00:00Z", { status: "scheduled" }), inputs())).toEqual({ kind: "none" });
    expect(hearingBusinessInfo(hearing("2026-11-07T00:00:00Z", { status: "scheduled" }), inputs())).toEqual({ kind: "none" });
    expect(hearingBusinessInfo(hearing("2026-10-20T00:00:00Z", { status: "cancelled" }), inputs())).toEqual({ kind: "none" });
  });

  it("shows an entry even for a hearing today, or a cancelled one", () => {
    const index = indexBusinessByDate([entry("2026-11-07"), entry("2026-10-20")]);
    expect(hearingBusinessInfo(hearing("2026-11-07T00:00:00Z", { status: "scheduled" }), inputs({ index })).kind).toBe("entry");
    expect(hearingBusinessInfo(hearing("2026-10-20T00:00:00Z", { status: "cancelled" }), inputs({ index })).kind).toBe("entry");
  });

  it("reports loading and error for hearings that could have a record, not for ones ahead", () => {
    expect(hearingBusinessInfo(hearing("2026-11-01T00:00:00Z"), inputs({ status: "loading" }))).toEqual({ kind: "loading" });
    expect(hearingBusinessInfo(hearing("2026-11-01T00:00:00Z"), inputs({ status: "error" }))).toEqual({ kind: "error" });
    expect(hearingBusinessInfo(hearing("2026-11-19T00:00:00Z", { status: "scheduled" }), inputs({ status: "loading" }))).toEqual({ kind: "none" });
  });
});

describe("oneLine", () => {
  it("collapses line breaks and runs of spaces", () => {
    expect(oneLine("  Petitioner present.\nRespondent   absent.\n")).toBe("Petitioner present. Respondent absent.");
  });
});

describe("checkErrorNote", () => {
  it("turns the server's cooldown into minutes", () => {
    const error = new APIError(429, { detail: "An order check just ran. Try again in a few minutes.", retry_after: 241 });
    expect(checkErrorNote(error)).toBe("A check just ran. Try again in about 5 min.");
    expect(checkErrorNote(new APIError(429, { retry_after: 20 }))).toBe("A check just ran. Try again in about 1 min.");
  });

  it("falls back to plain words when the cooldown has no length, and to the server's reason otherwise", () => {
    expect(checkErrorNote(new APIError(429, null))).toBe("A check just ran. Try again in a few minutes.");
    expect(checkErrorNote(new APIError(400, { detail: "Court tracking is not set up for this case." }))).toBe(
      "Court tracking is not set up for this case.",
    );
    expect(checkErrorNote(new Error("boom"))).toBe("Could not start the check. Try again in a moment.");
  });
});
