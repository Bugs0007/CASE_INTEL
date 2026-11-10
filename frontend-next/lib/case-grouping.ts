import { hearingDayKey } from "@/lib/calendar";
import type { Case } from "@/types";

/** Group the Cases list by court or by client. Plain TypeScript, no React.
 *
 * Grouping runs on the cases the page is already showing (after its search,
 * status and attention filters), so a group's count is what is on screen.
 *
 *  - Court: the case's court name, compared trimmed, whitespace-collapsed and
 *    case-insensitively ("Telangana High Court" and " telangana  high court"
 *    are one court). The group shows the spelling most of its cases use.
 *  - Client: the linked client's id when the case has one, else the typed
 *    client name compared the same way as a court.
 *  - A case with no court / no client goes in a last group of its own.
 *
 * Groups are ordered by the soonest upcoming hearing among their cases
 * (groups with none last, ties by name). Cases keep the order they came in. */

export type CaseGrouping = "none" | "court" | "client";

export const NO_COURT_LABEL = "No court set";
export const NO_CLIENT_LABEL = "No client";

export function parseGrouping(value: string | null | undefined): CaseGrouping | null {
  return value === "none" || value === "court" || value === "client" ? value : null;
}

export interface CaseGroup {
  /** Stable across renders and sessions: the collapsed state is saved under it. */
  key: string;
  label: string;
  /** The "No court set" / "No client" bucket. */
  missing: boolean;
  cases: Case[];
  /** India day (YYYY-MM-DD) of the soonest upcoming hearing, or null. */
  nextHearingDay: string | null;
}

const MISSING_KEY = "missing";

/** Trimmed, with runs of whitespace as one space. Case is kept. */
function tidy(text: string | null | undefined): string {
  return (text ?? "").replace(/\s+/g, " ").trim();
}

/** What two spellings of one name have in common. */
function fold(text: string | null | undefined): string {
  return tidy(text).toLowerCase();
}

interface Placement {
  key: string;
  /** This case's own spelling of the group's name ("" = none given). */
  spelling: string;
  missing: boolean;
}

function placeByCourt(c: Case): Placement {
  const spelling = tidy(c.court_name);
  return spelling ? { key: `n:${fold(spelling)}`, spelling, missing: false } : { key: MISSING_KEY, spelling: "", missing: true };
}

function placeByClient(c: Case): Placement {
  if (c.client_detail) {
    return { key: `i:${c.client_detail.id}`, spelling: tidy(c.client_detail.name) || tidy(c.client_name), missing: false };
  }
  const spelling = tidy(c.client_name);
  return spelling ? { key: `n:${fold(spelling)}`, spelling, missing: false } : { key: MISSING_KEY, spelling: "", missing: true };
}

/** The spelling used most often; on a tie, the one the list met first. */
function commonestSpelling(tally: Map<string, number>): string {
  let best = "";
  let bestCount = 0;
  for (const [spelling, count] of tally) {
    if (count > bestCount) {
      best = spelling;
      bestCount = count;
    }
  }
  return best;
}

/** `cases` as groups. `today` is the India day (YYYY-MM-DD) that "upcoming"
 * is measured from; "none" returns no groups (the caller shows the plain list). */
export function groupCases(cases: Case[], grouping: CaseGrouping, today: string): CaseGroup[] {
  if (grouping === "none") return [];
  const place = grouping === "court" ? placeByCourt : placeByClient;

  const buckets = new Map<string, { missing: boolean; cases: Case[]; spellings: Map<string, number>; next: string | null }>();
  for (const c of cases) {
    const p = place(c);
    let bucket = buckets.get(p.key);
    if (!bucket) {
      bucket = { missing: p.missing, cases: [], spellings: new Map(), next: null };
      buckets.set(p.key, bucket);
    }
    bucket.cases.push(c);
    if (p.spelling) bucket.spellings.set(p.spelling, (bucket.spellings.get(p.spelling) ?? 0) + 1);
    if (c.next_hearing_date) {
      const day = hearingDayKey(c.next_hearing_date);
      if (day >= today && (bucket.next === null || day < bucket.next)) bucket.next = day;
    }
  }

  const groups: CaseGroup[] = [];
  for (const [key, b] of buckets) {
    groups.push({
      key,
      label: b.missing ? (grouping === "court" ? NO_COURT_LABEL : NO_CLIENT_LABEL) : commonestSpelling(b.spellings) || "Unnamed",
      missing: b.missing,
      cases: b.cases,
      nextHearingDay: b.next,
    });
  }

  groups.sort((a, b) => {
    if (a.missing !== b.missing) return a.missing ? 1 : -1;
    if (a.nextHearingDay !== b.nextHearingDay) {
      if (a.nextHearingDay === null) return 1;
      if (b.nextHearingDay === null) return -1;
      return a.nextHearingDay < b.nextHearingDay ? -1 : 1;
    }
    const byName = a.label.localeCompare(b.label, "en", { sensitivity: "base" });
    if (byName !== 0) return byName;
    return a.key < b.key ? -1 : a.key > b.key ? 1 : 0;
  });
  return groups;
}
