import type { AdvocateResultRow, MatchStatus } from "@/types";

// Helpers for the redesigned advocate search's result list. The SERVER decides
// which rows are the advocate's own (core/services/advocate_results.py); what is
// here only (a) filters and counts rows already labelled, and (b) guesses the
// label a row will get after "Not me" / "That's me" so the screen can move at
// once, before the server's answer replaces the guess.

// ---------------------------------------------------------------------------
// Names (a mirror of the server's matching rule, for optimistic updates only)
// ---------------------------------------------------------------------------

const HONORIFIC_RE = /\b(?:adv|advocate|sri|shri|smt|mr|mrs|ms|dr|sr|jr)\b/gi;

export function nameTokens(name: string): string[] {
  return name
    .toLowerCase()
    .replace(HONORIFIC_RE, " ")
    .replace(/[.,;:/\\()\-_]+/g, " ")
    .split(/\s+/)
    .filter(Boolean);
}

function orderings(tokens: string[]): Set<string> {
  if (tokens.length > 3) return new Set([tokens.join("")]);
  const out = new Set<string>();
  const walk = (rest: string[], acc: string[]) => {
    if (rest.length === 0) {
      out.add(acc.join(""));
      return;
    }
    rest.forEach((t, i) => walk([...rest.slice(0, i), ...rest.slice(i + 1)], [...acc, t]));
  };
  walk(tokens, []);
  return out;
}

/** Same name ignoring spaces and, up to three words, word order. */
export function sameName(a: string, b: string): boolean {
  const ta = nameTokens(a);
  const tb = nameTokens(b);
  if (ta.length === 0 || tb.length === 0) return false;
  const oa = orderings(ta);
  return [...orderings(tb)].some((o) => oa.has(o));
}

/** The label a row will most likely get once the profile changes, for the
 * moment before the server answers. Rows that list the same name move; the
 * rest are left alone. */
export function relabelRows(
  rows: AdvocateResultRow[],
  name: string,
  action: "exclude" | "add",
): { rows: AdvocateResultRow[]; counts: Partial<Record<MatchStatus, number>> } {
  const single = nameTokens(name).length < 2;
  const next: AdvocateResultRow[] = rows.map((row) => {
    if (row.match_source === "bar_code") return row;
    const listed = row.listed_advocates?.length ? row.listed_advocates : row.listed_advocate_name ? [row.listed_advocate_name] : [];
    if (!listed.some((l) => sameName(l, name))) return row;
    if (action === "exclude") return { ...row, match_status: "excluded", match_label: "Hidden (Not me)" };
    return single
      ? { ...row, match_status: "check", match_label: "Check name" }
      : { ...row, match_status: "matched", match_label: "Your name" };
  });
  return { rows: next, counts: statusTotals(next) };
}

export function statusTotals(rows: AdvocateResultRow[]): Partial<Record<MatchStatus, number>> {
  const counts: Partial<Record<MatchStatus, number>> = { matched: 0, check: 0, excluded: 0, other: 0 };
  for (const row of rows) {
    const s = row.match_status ?? "check";
    counts[s] = (counts[s] ?? 0) + 1;
  }
  return counts;
}

// ---------------------------------------------------------------------------
// Filters (kept in the URL)
// ---------------------------------------------------------------------------

export type StatusChip = "all" | "pending" | "disposed";
export type MatchChip = "all" | "verified" | "check";

export interface ResultFilters {
  q: string;
  status: StatusChip;
  court: string;
  yearFrom: number | null;
  yearTo: number | null;
  match: MatchChip;
  showExcluded: boolean;
  showOther: boolean;
}

export const DEFAULT_FILTERS: ResultFilters = {
  q: "",
  status: "all",
  court: "",
  yearFrom: null,
  yearTo: null,
  match: "all",
  showExcluded: false,
  showOther: false,
};

const num = (v: string | null): number | null => {
  const n = v ? Number(v) : NaN;
  return Number.isInteger(n) && n > 1900 && n < 2200 ? n : null;
};

export function filtersFromParams(params: URLSearchParams): ResultFilters {
  const status = params.get("status");
  const match = params.get("match");
  return {
    q: params.get("q") ?? "",
    status: status === "pending" || status === "disposed" ? status : "all",
    court: params.get("court") ?? "",
    yearFrom: num(params.get("yf")),
    yearTo: num(params.get("yt")),
    match: match === "verified" || match === "check" ? match : "all",
    showExcluded: params.get("excl") === "1",
    showOther: params.get("other") === "1",
  };
}

/** Writes the non-default filters into `params` (and clears the default ones). */
export function filtersToParams(filters: ResultFilters, params: URLSearchParams): URLSearchParams {
  const set = (key: string, value: string | null) => (value ? params.set(key, value) : params.delete(key));
  set("q", filters.q || null);
  set("status", filters.status === "all" ? null : filters.status);
  set("court", filters.court || null);
  set("yf", filters.yearFrom ? String(filters.yearFrom) : null);
  set("yt", filters.yearTo ? String(filters.yearTo) : null);
  set("match", filters.match === "all" ? null : filters.match);
  set("excl", filters.showExcluded ? "1" : null);
  set("other", filters.showOther ? "1" : null);
  return params;
}

/** The year a case was registered: the field High Courts carry, else the year
 * at the end of the case number ("OS/740/2015"). */
export function rowYear(row: AdvocateResultRow): number | null {
  if (row.case_year) return row.case_year;
  const m = /\/(\d{4})\s*$/.exec(row.case_number ?? "");
  return m ? Number(m[1]) : null;
}

const courtOf = (row: AdvocateResultRow) => row.complex_name || row.court_name || "";

export function applyFilters(rows: AdvocateResultRow[], f: ResultFilters): AdvocateResultRow[] {
  const q = f.q.trim().toLowerCase();
  return rows.filter((row) => {
    const status = row.match_status ?? "check";
    if (status === "excluded" && !f.showExcluded) return false;
    if (status === "other" && !f.showOther) return false;
    if (f.match === "verified" && status !== "matched") return false;
    if (f.match === "check" && status !== "check") return false;
    const text = (row.status ?? "").toLowerCase();
    if (f.status === "pending" && !text.includes("pending")) return false;
    if (f.status === "disposed" && !text.includes("disposed")) return false;
    if (f.court && courtOf(row) !== f.court) return false;
    const year = rowYear(row);
    if (f.yearFrom && (year === null || year < f.yearFrom)) return false;
    if (f.yearTo && (year === null || year > f.yearTo)) return false;
    if (q) {
      const hay = [row.case_number, row.petitioner, row.respondent, row.listed_advocate_name, row.matched_advocate_text, courtOf(row)]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

/** Counts for the Pending / Disposed chips, over rows that pass every OTHER filter. */
export function statusCounts(rows: AdvocateResultRow[], f: ResultFilters): { pending: number; disposed: number; known: boolean } {
  const base = applyFilters(rows, { ...f, status: "all" });
  let pending = 0;
  let disposed = 0;
  for (const r of base) {
    const t = (r.status ?? "").toLowerCase();
    if (t.includes("pending")) pending += 1;
    else if (t.includes("disposed")) disposed += 1;
  }
  return { pending, disposed, known: rows.some((r) => /pending|disposed/i.test(r.status ?? "")) };
}

export function courtOptions(rows: AdvocateResultRow[]): string[] {
  return [...new Set(rows.map(courtOf).filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

export function yearBounds(rows: AdvocateResultRow[]): [number, number] | null {
  const years = rows.map(rowYear).filter((y): y is number => y !== null);
  return years.length ? [Math.min(...years), Math.max(...years)] : null;
}

// ---------------------------------------------------------------------------
// Time
// ---------------------------------------------------------------------------

/** Seconds a search is expected to take: one portal request per query per court. */
export function estimateSeconds(courts: number, queries: number, secondsPerCall: number): number {
  return Math.max(0, courts) * Math.max(1, queries) * secondsPerCall;
}

/** "about 6 minutes", "under 1 minute". */
export function describeEstimate(seconds: number): string {
  if (seconds < 60) return "under 1 minute";
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `about ${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.round((seconds / 3600) * 10) / 10;
  return `about ${hours} hours`;
}

/** 161 -> "2:41". */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** 38 -> "38 s", 125 -> "2 min". */
export function formatShort(seconds: number): string {
  return seconds < 90 ? `${Math.round(seconds)} s` : `${Math.round(seconds / 60)} min`;
}
