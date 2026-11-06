import { describe, it, expect } from "vitest";
import {
  addDays,
  dateLabel,
  daysBetween,
  greetingFor,
  istDayKey,
  longDate,
  shortDay,
} from "@/lib/dashboard/dates";
import { clip, countOf, lowerFirst, numberWord } from "@/lib/dashboard/text";
import {
  buildBands,
  buildDashboardModel,
  buildDays,
  buildInsights,
  buildNeeds,
  classifyCases,
  comingUp,
  comingUpSegments,
  defaultSelection,
  describeHearing,
  firstParty,
  insightSegments,
  leadSentence,
  needSegments,
  practiceCounts,
  sinceSummary,
  todaysHearings,
  type ClassifyInput,
  type DashCase,
  type DashHearing,
  type DashTask,
  type Seg,
} from "@/lib/dashboard/model";

// Thursday 5 November 2026.
const TODAY = "2026-11-05";

function hearing(overrides: Partial<DashHearing> & { id: number }): DashHearing {
  return {
    caseId: overrides.id,
    caseTitle: `Case ${overrides.id}`,
    day: TODAY,
    court: "Telangana High Court",
    hall: "",
    item: "",
    state: "listed",
    scheduled: true,
    ...overrides,
  };
}

function kase(id: number, overrides: Partial<DashCase> = {}): DashCase {
  return { id, title: `Case ${id}`, number: `WP/${id}/2026`, status: "open", courtFallback: "", ...overrides };
}

function task(id: number, overrides: Partial<DashTask> = {}): DashTask {
  return { id, caseId: 1, caseTitle: "Case 1", title: "File counter affidavit", due: null, kind: "manual", ...overrides };
}

const text = (segs: Seg[]) => segs.map((s) => s.text).join("");

describe("number words and plurals", () => {
  it("spells out to nine, then digits", () => {
    expect(numberWord(1)).toBe("one");
    expect(numberWord(2)).toBe("two");
    expect(numberWord(9)).toBe("nine");
    expect(numberWord(10)).toBe("10");
    expect(numberWord(12)).toBe("12");
  });

  it("pluralises", () => {
    expect(countOf(1, "hearing")).toBe("1 hearing");
    expect(countOf(14, "hearing")).toBe("14 hearings");
    expect(countOf(1, "day")).toBe("1 day");
  });

  it("lower-cases only the first letter, so names keep their capitals", () => {
    expect(lowerFirst("Respondent No.2 shall file the Telangana HC form")).toBe(
      "respondent No.2 shall file the Telangana HC form",
    );
  });

  it("clips long text at a word boundary", () => {
    const long = "word ".repeat(100);
    const out = clip(long, 50);
    expect(out.length).toBeLessThanOrEqual(51);
    expect(out.endsWith("…")).toBe(true);
    expect(clip("short", 50)).toBe("short");
  });
});

describe("date handling (India, date-only)", () => {
  it("builds day offsets without a UTC shift", () => {
    expect(addDays("2026-11-05", 1)).toBe("2026-11-06");
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(daysBetween("2026-11-05", "2026-11-19")).toBe(14);
    expect(daysBetween("2026-11-05", "2026-11-03")).toBe(-2);
  });

  it("labels Today, Tomorrow, then weekday + day + month", () => {
    expect(dateLabel("2026-11-05", TODAY)).toBe("Today");
    expect(dateLabel("2026-11-06", TODAY)).toBe("Tomorrow");
    expect(dateLabel("2026-11-07", TODAY)).toBe("Sat 7 Nov");
    expect(shortDay("2026-11-06")).toBe("Fri 6 Nov");
    expect(longDate(TODAY)).toBe("Thursday, 5 November 2026");
  });

  it("takes today's date from India, not from UTC", () => {
    // 00:30 IST on the 6th is 19:00 UTC on the 5th.
    expect(istDayKey(new Date("2026-11-05T19:00:00Z"))).toBe("2026-11-06");
    // 23:30 IST on the 5th is 18:00 UTC on the 5th.
    expect(istDayKey(new Date("2026-11-05T18:00:00Z"))).toBe("2026-11-05");
    // Just before IST midnight vs just after.
    expect(istDayKey(new Date("2026-11-05T18:29:59Z"))).toBe("2026-11-05");
    expect(istDayKey(new Date("2026-11-05T18:30:00Z"))).toBe("2026-11-06");
  });

  it("greets by the hour", () => {
    expect(greetingFor(0)).toBe("Good morning");
    expect(greetingFor(11)).toBe("Good morning");
    expect(greetingFor(12)).toBe("Good afternoon");
    expect(greetingFor(16)).toBe("Good afternoon");
    expect(greetingFor(17)).toBe("Good evening");
    expect(greetingFor(23)).toBe("Good evening");
  });
});

describe("todaysHearings", () => {
  it("keeps only scheduled hearings today, listed first, then court, hall, item", () => {
    const list = todaysHearings(
      [
        hearing({ id: 1, state: "not_listed" }),
        hearing({ id: 2, court: "B Court", hall: "2", item: "9" }),
        hearing({ id: 3, court: "A Court", hall: "10", item: "1" }),
        hearing({ id: 4, court: "A Court", hall: "2", item: "30" }),
        hearing({ id: 5, court: "A Court", hall: "2", item: "4" }),
        hearing({ id: 6, scheduled: false }),
        hearing({ id: 7, day: "2026-11-06" }),
      ],
      TODAY,
    );
    expect(list.map((h) => h.id)).toEqual([5, 4, 3, 2, 1]);
  });
});

describe("leadSentence", () => {
  const next = [hearing({ id: 9, day: "2026-11-06" })];

  it("says 'No hearings today' and names the next court day", () => {
    expect(leadSentence([], next, TODAY)).toBe("No hearings today. Your next court day is tomorrow.");
    expect(leadSentence([], [hearing({ id: 9, day: "2026-11-12" })], TODAY)).toBe(
      "No hearings today. Your next court day is Thu 12 Nov.",
    );
  });

  it("says so when nothing is due in two weeks", () => {
    expect(leadSentence([], [], TODAY)).toBe("No hearings in the next two weeks.");
    expect(leadSentence([], [hearing({ id: 9, day: "2026-12-30" })], TODAY)).toBe(
      "No hearings in the next two weeks.",
    );
  });

  it("uses singular and number words", () => {
    const one = [hearing({ id: 1 })];
    expect(leadSentence(one, one, TODAY)).toBe("One hearing today.");
    const two = [hearing({ id: 1 }), hearing({ id: 2 })];
    expect(leadSentence(two, two, TODAY)).toBe("Two hearings today.");
    const many = Array.from({ length: 12 }, (_, i) => hearing({ id: i + 1 }));
    expect(leadSentence(many, many, TODAY)).toBe("12 hearings today.");
  });

  it("counts only genuine not_listed as missing from the cause list", () => {
    const hs = [
      hearing({ id: 1, state: "listed" }),
      hearing({ id: 2, state: "not_listed" }),
      hearing({ id: 3, state: "unsupported" }),
      hearing({ id: 4, state: "not_checked" }),
      hearing({ id: 5, state: "not_published" }),
      hearing({ id: 6, state: "fetch_failed" }),
    ];
    expect(leadSentence(hs, hs, TODAY)).toBe("Six hearings today, and one is not on the cause list.");
    const two = [hearing({ id: 1, state: "not_listed" }), hearing({ id: 2, state: "not_listed" })];
    expect(leadSentence(two, two, TODAY)).toBe("Two hearings today, and 2 are not on the cause list.");
    const none = [hearing({ id: 1, state: "unsupported" })];
    expect(leadSentence(none, none, TODAY)).toBe("One hearing today.");
  });
});

describe("describeHearing wording per cause-list state", () => {
  const ctx = { today: TODAY };

  it("listed: item, hall, court, last order and what you owe", () => {
    const segs = describeHearing(
      hearing({ id: 1, caseTitle: "Butham vs State", state: "listed", item: "22", hall: "4" }),
      {
        ...ctx,
        lastOrder: { day: "2026-10-20", text: "Interim direction to consider the representation." },
        task: { title: "File proof of deposit", due: "2026-11-06" },
      },
    );
    expect(text(segs)).toBe(
      "Butham vs State is listed at item 22, hall 4, Telangana High Court. " +
        "The last order (20 Oct) said interim direction to consider the representation. " +
        "You owe file proof of deposit by tomorrow.",
    );
    expect(segs[0]).toMatchObject({ kind: "case", caseId: 1 });
    expect(segs.find((s) => s.kind === "em")?.text).toBe("interim direction to consider the representation");
    expect(segs.find((s) => s.kind === "strong")?.text).toBe("file proof of deposit");
  });

  it("listed: no open task means no 'You owe' sentence; no order means no 'last order' sentence", () => {
    const out = text(describeHearing(hearing({ id: 1, item: "3", hall: "1" }), ctx));
    expect(out).toBe("Case 1 is listed at item 3, hall 1, Telangana High Court.");
    expect(out).not.toContain("owe");
    expect(out).not.toContain("last order");
  });

  it("listed: an overdue task says so", () => {
    const out = text(
      describeHearing(hearing({ id: 1, item: "3" }), { ...ctx, task: { title: "Serve notice", due: "2026-11-03" } }),
    );
    expect(out).toContain("You owe serve notice by Tue 3 Nov (overdue).");
  });

  it("not_listed on a covered court: says it is not on today's list", () => {
    const out = text(describeHearing(hearing({ id: 1, state: "not_listed" }), ctx));
    expect(out).toContain("is not on today's cause list.");
    expect(out).toContain("check the court's site before you leave");
  });

  it("not_published", () => {
    expect(text(describeHearing(hearing({ id: 1, state: "not_published", court: "Bombay High Court" }), ctx))).toContain(
      "The cause list for Bombay High Court is not published yet.",
    );
  });

  it.each(["unsupported", "not_checked"] as const)(
    "%s never says 'not listed' or 'not on the cause list'",
    (state) => {
      const out = text(describeHearing(hearing({ id: 1, state, court: "Hyderabad Civil Court" }), ctx));
      expect(out).toContain("Cause lists are not tracked for Hyderabad Civil Court, so check the court's site.");
      expect(out.toLowerCase()).not.toContain("not listed");
      expect(out.toLowerCase()).not.toContain("not on");
    },
  );

  it("fetch_failed says it could not check, not that the case is missing", () => {
    const out = text(describeHearing(hearing({ id: 1, state: "fetch_failed" }), ctx));
    expect(out).toContain("couldn't check the cause list");
    expect(out.toLowerCase()).not.toContain("not listed");
  });

  it("falls back to 'this court' when the court is unknown", () => {
    const out = text(describeHearing(hearing({ id: 1, state: "unsupported", court: "" }), ctx));
    expect(out).toContain("not tracked for this court");
  });

  it("only the listed sentence carries the task sentence", () => {
    const out = text(
      describeHearing(hearing({ id: 1, state: "not_listed" }), {
        ...ctx,
        task: { title: "File x", due: "2026-11-06" },
      }),
    );
    expect(out).not.toContain("You owe");
  });
});

describe("sinceSummary", () => {
  const hearings = [
    hearing({ id: 1, caseId: 1, day: "2026-11-10", court: "High Court" }),
    hearing({ id: 2, caseId: 2, day: "2026-11-10", court: "Civil Court" }),
    hearing({ id: 3, caseId: 3, day: "2026-11-12", court: "High Court" }),
    hearing({ id: 4, caseId: 4, day: "2026-11-12", court: "Civil Court" }),
  ];

  it("counts cases (not hearings) and finds the earliest new date", () => {
    const s = sinceSummary(
      [
        { hearingId: 1, caseId: 1, day: "2026-11-10" },
        { hearingId: 11, caseId: 1, day: "2026-11-20" },
        { hearingId: 3, caseId: 3, day: "2026-11-12" },
      ],
      hearings,
      TODAY,
    );
    expect(s.count).toBe(2);
    expect(s.earliest).toBe("2026-11-10");
  });

  it("reports a clash only on a day that holds a hearing eCourts just moved", () => {
    // 10 Nov has two courts and hearing 1 just moved there.
    const moved = sinceSummary([{ hearingId: 1, caseId: 1, day: "2026-11-10" }], hearings, TODAY);
    expect(moved.clash).toEqual({ day: "2026-11-10", courts: 2 });
  });

  it("ignores a clash on a day where nothing changed", () => {
    // 12 Nov also has two courts, but the only changed hearing is elsewhere.
    const none = sinceSummary(
      [{ hearingId: 99, caseId: 9, day: "2026-11-30" }],
      hearings,
      TODAY,
    );
    expect(none.count).toBe(1);
    expect(none.clash).toBeNull();
  });

  it("picks the earliest clashing day that involves a changed case", () => {
    const s = sinceSummary(
      [
        { hearingId: 3, caseId: 3, day: "2026-11-12" },
        { hearingId: 1, caseId: 1, day: "2026-11-10" },
      ],
      hearings,
      TODAY,
    );
    expect(s.clash?.day).toBe("2026-11-10");
  });

  it("does not count hearings today or unknown courts as a clash", () => {
    const hs = [
      hearing({ id: 1, caseId: 1, day: TODAY, court: "A" }),
      hearing({ id: 2, caseId: 2, day: TODAY, court: "B" }),
      hearing({ id: 3, caseId: 3, day: "2026-11-09", court: "A" }),
      hearing({ id: 4, caseId: 4, day: "2026-11-09", court: "" }),
    ];
    const s = sinceSummary(
      [
        { hearingId: 1, caseId: 1, day: TODAY },
        { hearingId: 3, caseId: 3, day: "2026-11-09" },
      ],
      hs,
      TODAY,
    );
    expect(s.clash).toBeNull();
  });

  it("is empty when nothing changed", () => {
    expect(sinceSummary([], hearings, TODAY)).toEqual({ count: 0, items: [], earliest: null, clash: null });
  });
});

describe("the next 14 days", () => {
  const hs = [
    hearing({ id: 1, day: TODAY, court: "A" }),
    hearing({ id: 2, day: "2026-11-10", court: "A" }),
    hearing({ id: 3, day: "2026-11-10", court: "B" }),
    hearing({ id: 4, day: "2026-11-10", court: "B" }),
    hearing({ id: 5, day: "2026-11-18", court: "A" }), // day 13
    hearing({ id: 6, day: "2026-11-19", court: "A" }), // day 14: outside
    hearing({ id: 7, day: "2026-11-11", scheduled: false }),
  ];

  it("buckets fourteen days from today and marks days with 2+ courts", () => {
    const days = buildDays(hs, TODAY);
    expect(days).toHaveLength(14);
    expect(days[0]).toMatchObject({ day: TODAY, label: "Today", count: 1, multiCourt: false });
    expect(days[5]).toMatchObject({ day: "2026-11-10", count: 3, multiCourt: true, courts: ["A", "B"] });
    expect(days[6].count).toBe(0);
    expect(days[13]).toMatchObject({ day: "2026-11-18", count: 1 });
  });

  it("finds the busiest day (earliest on a tie) and the total", () => {
    const c = comingUp(buildDays(hs, TODAY));
    expect(c.total).toBe(5);
    expect(c.busiest).toEqual({ day: "2026-11-10", count: 3, courts: 2 });
    expect(text(comingUpSegments(c, TODAY))).toBe(
      "5 hearings in the next 14 days. The busiest day is Tue 10 Nov with 3, across 2 courts.",
    );
  });

  it("drops 'across k courts' for one court, and handles one hearing and none", () => {
    const one = comingUp(buildDays([hearing({ id: 1, day: "2026-11-08", court: "A" })], TODAY));
    expect(text(comingUpSegments(one, TODAY))).toBe(
      "1 hearing in the next 14 days. The busiest day is Sun 8 Nov with 1.",
    );
    expect(text(comingUpSegments(comingUp(buildDays([], TODAY)), TODAY))).toBe(
      "No hearings in the next 14 days.",
    );
  });

  it("breaks a tie by the earlier day", () => {
    const tie = comingUp(
      buildDays(
        [
          hearing({ id: 1, day: "2026-11-12" }),
          hearing({ id: 2, day: "2026-11-08" }),
        ],
        TODAY,
      ),
    );
    expect(tie.busiest?.day).toBe("2026-11-08");
  });
});

describe("needs you", () => {
  it("merges everything, dated first with overdue leading, undated last", () => {
    const needs = buildNeeds({
      tasks: [
        task(1, { due: "2026-11-09", title: "File reply" }),
        task(2, { due: "2026-11-02", title: "Serve notice" }),
        task(3, { due: null, title: "Call client" }),
      ],
      failedDocs: [{ id: 7, caseId: 1, caseTitle: "Case 1", filename: "order.pdf" }],
      unbilled: [{ hearingId: 8, caseId: 2, caseTitle: "Case 2", day: "2026-10-28" }],
      drafts: [{ id: 9, caseId: 3, caseTitle: "Case 3", kind: "case_update" }],
    });
    expect(needs.map((n) => n.key)).toEqual(["task-2", "task-1", "task-3", "unbilled-8", "draft-9", "doc-7"]);
  });

  it("words each item: title, lower-cased action, then days overdue or due date", () => {
    const today = TODAY;
    const mk = (due: string | null, title = "File proof of deposit") =>
      text(
        needSegments(buildNeeds({ tasks: [task(1, { due, title })], failedDocs: [], unbilled: [], drafts: [] })[0], today),
      );
    expect(mk("2026-11-02")).toBe("Case 1: file proof of deposit, 3 days overdue.");
    expect(mk("2026-11-04")).toBe("Case 1: file proof of deposit, 1 day overdue.");
    expect(mk("2026-11-05")).toBe("Case 1: file proof of deposit, due today.");
    expect(mk("2026-11-06")).toBe("Case 1: file proof of deposit, due tomorrow.");
    expect(mk("2026-11-06".replace("06", "13"))).toBe("Case 1: file proof of deposit, due Fri 13 Nov.");
    expect(mk(null)).toBe("Case 1: file proof of deposit.");
  });

  it("words the non-task items", () => {
    const [unbilled] = buildNeeds({
      tasks: [],
      failedDocs: [],
      unbilled: [{ hearingId: 8, caseId: 2, caseTitle: "Case 2", day: "2026-10-28" }],
      drafts: [],
    });
    expect(text(needSegments(unbilled, TODAY))).toBe("Case 2: the appearance on 28 Oct is not invoiced.");
    const [draft] = buildNeeds({
      tasks: [],
      failedDocs: [],
      unbilled: [],
      drafts: [{ id: 9, caseId: 3, caseTitle: "Case 3", kind: "payment_reminder" }],
    });
    expect(text(needSegments(draft, TODAY))).toBe("Case 3: a payment reminder draft is waiting for review.");
  });

  it("is empty when nothing is waiting", () => {
    expect(buildNeeds({ tasks: [], failedDocs: [], unbilled: [], drafts: [] })).toEqual([]);
  });

  it("a task with no case reads as a plain sentence", () => {
    const [item] = buildNeeds({
      tasks: [task(1, { caseId: null, caseTitle: "", title: "renew bar card", due: "2026-11-09" })],
      failedDocs: [],
      unbilled: [],
      drafts: [],
    });
    expect(text(needSegments(item, TODAY))).toBe("Renew bar card, due Mon 9 Nov.");
  });
});

describe("practice map classification", () => {
  function input(overrides: Partial<ClassifyInput> = {}): ClassifyInput {
    return {
      today: TODAY,
      cases: [],
      hearings: [],
      tasks: [],
      changed: [],
      failedDocs: [],
      unbilled: [],
      drafts: [],
      ...overrides,
    };
  }
  const statusOf = (i: ClassifyInput, id = 1) => classifyCases(i).find((c) => c.id === id)!;

  it("hearing today", () => {
    const c = statusOf(
      input({ cases: [kase(1)], hearings: [hearing({ id: 1, caseId: 1, item: "22" })] }),
    );
    expect(c.status).toBe("today");
    expect(c.reason).toBe("Today · item 22");
  });

  it("needs action: an order task, an uninvoiced hearing, a draft, a failed document, or no next date", () => {
    const base = { cases: [kase(1)], hearings: [hearing({ id: 1, caseId: 1, day: "2026-12-30" })] };
    expect(statusOf(input({ ...base, tasks: [task(1, { kind: "order_direction" })] })).reason).toBe("Order task");
    expect(
      statusOf(input({ ...base, unbilled: [{ hearingId: 5, caseId: 1, caseTitle: "x", day: "2026-10-28" }] })).reason,
    ).toBe("Not invoiced");
    expect(statusOf(input({ ...base, drafts: [{ id: 1, caseId: 1, caseTitle: "x", kind: "case_update" }] })).reason).toBe(
      "Draft waiting",
    );
    expect(statusOf(input({ ...base, failedDocs: [{ id: 1, caseId: 1, caseTitle: "x", filename: "a.pdf" }] })).reason).toBe(
      "Document failed",
    );
    const noDate = statusOf(input({ cases: [kase(1)] }));
    expect(noDate.status).toBe("attn");
    expect(noDate.reason).toBe("No next date");
  });

  it("a manual task alone is not an attention flag", () => {
    const c = statusOf(
      input({
        cases: [kase(1)],
        hearings: [hearing({ id: 1, caseId: 1, day: "2026-12-30" })],
        tasks: [task(1, { kind: "manual" })],
      }),
    );
    expect(c.status).toBe("quiet");
  });

  it("hearing within seven days is 'this week'; day eight is not", () => {
    const at = (day: string) =>
      statusOf(input({ cases: [kase(1)], hearings: [hearing({ id: 1, caseId: 1, day })] }));
    expect(at("2026-11-06").status).toBe("week");
    expect(at("2026-11-12").status).toBe("week");
    expect(at("2026-11-12").reason).toBe("Hearing Thu 12 Nov");
    expect(at("2026-11-13").status).toBe("quiet");
  });

  it("an unseen new date from eCourts, when nothing outranks it", () => {
    const c = statusOf(
      input({
        cases: [kase(1)],
        hearings: [hearing({ id: 1, caseId: 1, day: "2026-12-14" })],
        changed: [{ hearingId: 1, caseId: 1, day: "2026-12-14" }],
      }),
    );
    expect(c.status).toBe("ecourts");
    expect(c.reason).toBe("New date 14 Dec");
  });

  it("precedence: today > needs action > this week > new date > quiet", () => {
    const cases = [kase(1), kase(2), kase(3), kase(4), kase(5)];
    const hearings = [
      hearing({ id: 1, caseId: 1, day: TODAY }),
      hearing({ id: 2, caseId: 2, day: "2026-11-08" }),
      hearing({ id: 3, caseId: 3, day: "2026-11-08" }),
      hearing({ id: 4, caseId: 4, day: "2026-12-20" }),
      hearing({ id: 5, caseId: 5, day: "2026-12-20" }),
    ];
    const out = classifyCases(
      input({
        cases,
        hearings,
        // case 1: today AND a task AND a new date
        // case 2: this week AND a task
        // case 3: this week AND a new date
        // case 4: a new date only
        tasks: [task(1, { caseId: 1, kind: "order_direction" }), task(2, { caseId: 2, kind: "order_direction" })],
        changed: [
          { hearingId: 1, caseId: 1, day: TODAY },
          { hearingId: 3, caseId: 3, day: "2026-11-08" },
          { hearingId: 4, caseId: 4, day: "2026-12-20" },
        ],
      }),
    );
    expect(Object.fromEntries(out.map((c) => [c.id, c.status]))).toEqual({
      1: "today",
      2: "attn",
      3: "week",
      4: "ecourts",
      5: "quiet",
    });
  });

  it("closed and archived cases are not on the map", () => {
    const out = classifyCases(
      input({ cases: [kase(1), kase(2, { status: "closed" }), kase(3, { status: "archived" })] }),
    );
    expect(out.map((c) => c.id)).toEqual([1]);
  });

  it("a hearing that is not scheduled does not make a case 'today'", () => {
    const c = statusOf(
      input({ cases: [kase(1)], hearings: [hearing({ id: 1, caseId: 1, scheduled: false })] }),
    );
    expect(c.status).toBe("attn");
    expect(c.reason).toBe("No next date");
  });

  it("legend counts add up to the cases shown", () => {
    const out = classifyCases(
      input({
        cases: [kase(1), kase(2), kase(3)],
        hearings: [hearing({ id: 1, caseId: 1 }), hearing({ id: 2, caseId: 2, day: "2026-12-30" })],
      }),
    );
    const counts = practiceCounts(out);
    expect(counts).toEqual({ today: 1, attn: 1, week: 0, ecourts: 0, quiet: 1 });
    expect(Object.values(counts).reduce((a, b) => a + b, 0)).toBe(out.length);
  });

  it("names the court from the newest hearing that has one, else a fallback", () => {
    const out = classifyCases(
      input({
        cases: [kase(1), kase(2, { courtFallback: "High Court" }), kase(3)],
        hearings: [
          hearing({ id: 1, caseId: 1, day: "2026-09-01", court: "Old Court" }),
          hearing({ id: 2, caseId: 1, day: "2026-12-01", court: "New Court" }),
          hearing({ id: 3, caseId: 1, day: "2026-12-02", court: "" }),
        ],
      }),
    );
    expect(out.map((c) => c.court)).toEqual(["New Court", "High Court", "Court not recorded"]);
  });

  it("builds bands busiest-first, with tiles for action and squares for the rest", () => {
    const practice = classifyCases(
      input({
        cases: [kase(1), kase(2), kase(3), kase(4)],
        hearings: [
          hearing({ id: 1, caseId: 1, court: "Big Court" }), // today
          hearing({ id: 2, caseId: 2, court: "Big Court", day: "2026-12-30" }), // quiet
          hearing({ id: 3, caseId: 3, court: "Big Court", day: "2026-12-30" }), // new date
          hearing({ id: 4, caseId: 4, court: "Small Court", day: "2026-11-07" }), // week
        ],
        changed: [{ hearingId: 3, caseId: 3, day: "2026-12-30" }],
      }),
    );
    const bands = buildBands(practice);
    expect(bands.map((b) => b.court)).toEqual(["Big Court", "Small Court"]);
    expect(bands[0]).toMatchObject({ needLook: 1, newDates: 1, quiet: 1 });
    expect(bands[0].tiles.map((c) => c.id)).toEqual([1]);
    expect(bands[0].squares.map((c) => c.id)).toEqual([3, 2]); // new date before quiet
    expect(bands[1].tiles.map((c) => c.id)).toEqual([4]);
  });

  it("picks the most urgent case as the default selection", () => {
    const practice = classifyCases(
      input({
        cases: [kase(1), kase(2)],
        hearings: [
          hearing({ id: 1, caseId: 1, day: "2026-12-30" }),
          hearing({ id: 2, caseId: 2, day: TODAY }),
        ],
      }),
    );
    expect(defaultSelection(practice)).toBe(2);
    expect(defaultSelection([])).toBeNull();
  });

  it("takes the first party out of a title", () => {
    expect(firstParty("Butham Srinivas vs State of Telangana")).toBe("Butham Srinivas");
    expect(firstParty("A Kumar v. B Rao")).toBe("A Kumar");
    expect(firstParty("WP/1709/2026")).toBe("WP/1709/2026");
  });
});

describe("heads-up insights", () => {
  it("reports a day with hearings in two courts and cases with no next date", () => {
    const days = buildDays(
      [hearing({ id: 1, day: "2026-11-12", court: "A" }), hearing({ id: 2, day: "2026-11-12", court: "B" })],
      TODAY,
    );
    const practice = classifyCases({
      today: TODAY,
      cases: [kase(1), kase(2), kase(3)],
      hearings: [hearing({ id: 1, caseId: 1, day: "2026-11-12" })],
      tasks: [],
      changed: [],
      failedDocs: [],
      unbilled: [],
      drafts: [],
    });
    const insights = buildInsights(days, practice);
    expect(insights.map((i) => text(insightSegments(i)))).toEqual([
      "Thu 12 Nov has hearings in 2 courts: A, B.",
      "2 cases have no next hearing date. Refresh to check eCourts.",
    ]);
  });

  it("is empty when nothing applies", () => {
    expect(buildInsights(buildDays([], TODAY), [])).toEqual([]);
  });

  it("uses the singular for one case", () => {
    const [insight] = buildInsights(buildDays([], TODAY), [
      { ...classifyCases({ today: TODAY, cases: [kase(1)], hearings: [], tasks: [], changed: [], failedDocs: [], unbilled: [], drafts: [] })[0] },
    ]);
    expect(text(insightSegments(insight))).toBe("1 case has no next hearing date. Refresh to check eCourts.");
  });
});

describe("buildDashboardModel", () => {
  it("shares one classification between the legend, the bands and the sentences", () => {
    const model = buildDashboardModel({
      today: TODAY,
      cases: [kase(1), kase(2)],
      hearings: [hearing({ id: 1, caseId: 1, item: "5", hall: "2" }), hearing({ id: 2, caseId: 2, day: "2026-12-30" })],
      tasks: [task(1, { caseId: 1, due: "2026-11-08" })],
      changed: [],
      failedDocs: [],
      unbilled: [],
      drafts: [],
      lastOrders: new Map([[1, { day: "2026-10-20", text: "Stay extended." }]]),
    });
    expect(model.dateLine).toBe("Thursday, 5 November 2026");
    expect(model.activeCaseCount).toBe(2);
    expect(model.lead).toBe("One hearing today.");
    expect(text(model.todays[0].segments)).toBe(
      "Case 1 is listed at item 5, hall 2, Telangana High Court. The last order (20 Oct) said stay extended. You owe file counter affidavit by Sun 8 Nov.",
    );
    expect(model.counts.today + model.counts.attn + model.counts.week + model.counts.ecourts + model.counts.quiet).toBe(
      model.practice.length,
    );
    expect(model.bands.reduce((n, b) => n + b.cases.length, 0)).toBe(model.practice.length);
    expect(model.openTaskCount.get(1)).toBe(1);
  });
});
