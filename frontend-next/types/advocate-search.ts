import type { CourtType } from "./case";
import type { ConflictHit } from "./conflict";

/** One eCourts search result -- a subset of bharat_courts' CaseInfo.to_dict()
 * shape, as returned by POST /api/cases/search-advocate/. */
export interface AdvocateSearchResult {
  case_number: string;
  case_type: string;
  cnr_number: string;
  filing_number: string;
  registration_number: string;
  registration_date: string | null;
  petitioner: string;
  respondent: string;
  status: string;
  court_name: string;
  judges: string[];
  next_hearing_date: string | null;
  /** True only when the court's response carried an advocate for this row
   * AND it shared a real name token with the search. False/absent means it
   * could not be checked (no advocate column for this court complex, a
   * blank cell, or a bar-code search -- eCourts never publishes bar codes
   * here). Absent on results saved before verification existed; treat as
   * unverified. Never a mismatch: mismatches are dropped server-side. */
  advocate_match_verified?: boolean;
  /** The advocate text the court recorded for this row, when it reported
   * one -- shown so a human can tell a genuine match from a different
   * advocate who merely shares the name (e.g. a government prosecutor). */
  matched_advocate_text?: string | null;
}

export interface AdvocateSearchRequest {
  name_or_bar_code: string;
  court_type: CourtType;
  /** The user always picks a STATE; the backend fans out across every
   * district and court complex in it -- unless dist_codes narrows it to
   * the districts where the advocate practices (fast path). Omit or send
   * [] for the whole state. */
  state_code: string;
  dist_codes?: string[];
  /** "quick" searches only the court complexes remembered from earlier
   * searches for this advocate (the server answers 400 code
   * "no_quick_history" when there are none). Default "full". */
  mode?: "full" | "quick";
  status_filter?: "Pending" | "Disposed" | "Both";
}

/** How a search was scoped: the whole state, chosen districts, or only the
 * remembered court complexes. */
export type AdvocateSearchMode = "state" | "districts" | "quick";

export type AdvocateSearchJobStatus = "queued" | "running" | "succeeded" | "partial" | "failed" | "cancelled";

/** One court complex that was skipped during the fan-out (CAPTCHA/portal
 * error). court_complex is null when the district's complex-list call
 * itself failed. error_type distinguishes WHY, for both display and
 * whether a retry is likely to help: "session" (the portal rejected the
 * request before captcha, worth retrying), "captcha" (a wrong OCR guess,
 * already retried per-attempt), "data" (a bad district/complex code,
 * retrying won't help), "portal" (anything else). */
export interface AdvocateSearchFailure {
  district: string;
  court_complex: string | null;
  error: string;
  error_type?: "session" | "captcha" | "data" | "portal";
}

/** Per-district rollup, keyed by eCourts district code. */
export interface AdvocateSearchDistrictStatus {
  name: string;
  status: "success" | "failed" | "partial";
  complexes_total: number;
  complexes_ok: number;
  complexes_failed: number;
}

/** POST /api/cases/search-advocate/ enqueues a job and returns its id. */
export interface AdvocateSearchStartResponse {
  job_id: number;
}

/** GET /api/cases/search-advocate/<job_id>/ -- progress is
 * districts_done / total_districts for the districts THIS job is
 * covering (the whole state, one district, or a failed-districts retry
 * subset). results/failures/districts_status are populated
 * INCREMENTALLY as districts complete, even while status is "running". */
export interface AdvocateSearchJobResult {
  status: AdvocateSearchJobStatus;
  progress_current: number;
  progress_total: number;
  error: string;
  /** Capped at MAX_RESULTS_IN_RESPONSE server-side -- may be a prefix of
   * results_total. A state-wide search on a common name matches tens of
   * thousands of cases, and returning them all took the API down. */
  results: AdvocateResultRow[];
  /** The real match count, which may exceed results.length. */
  results_total: number;
  results_truncated: boolean;
  failures: AdvocateSearchFailure[];
  districts_total: number | null;
  districts_status: Record<string, AdvocateSearchDistrictStatus>;
  /** Court complexes read successfully so far. */
  complexes_searched: number | null;
  /** Court complexes attempted so far, read or not. */
  complexes_done: number | null;
  /** Complexes in the districts listed so far -- a district's count is
   * known once it is listed, so this grows as the run goes. */
  complexes_total_known: number | null;
  current_district: string;
  mode: AdvocateSearchMode;
  created_at: string;
  /** Null while the job is still waiting for the worker. */
  started_at: string | null;
  /** Redesigned search only (absent on an old job): the profile the rows are
   * labelled against, the count of each label over ALL rows, and what kind of
   * search it was. */
  profile_id?: number | null;
  match_counts?: Partial<Record<MatchStatus, number>>;
  v2?: boolean;
  court_type?: CourtType;
  search_by?: "names" | "bar_code" | "";
  queries?: string[];
  state_code?: string;
  hc_court_name?: string;
}

/** Courts remembered for an advocate from earlier searches (Quick search). */
export interface QuickSearchSummary {
  complexes: number;
  districts: number;
  updated_at: string | null;
}

export interface AdvocateSearchPreference {
  court_type: CourtType;
  /** The last state searched, and the districts picked for it (none =
   * all districts). Court complexes are discovered server-side. */
  hierarchy_config: { state_code?: string; dist_codes?: string[] };
  /** Present when asked about a name + state: null if nothing is
   * remembered for them yet. */
  quick_search: QuickSearchSummary | null;
}

export interface AdvocateImportSelection {
  cnr_number: string;
  case_number: string;
  petitioner: string;
  respondent: string;
  court_name: string;
}

export interface AdvocateImportStartResponse {
  job_id: number;
}

export type AdvocateImportJobStatus = "queued" | "running" | "succeeded" | "failed";

export interface AdvocateImportJobResult {
  status: AdvocateImportJobStatus;
  progress_current: number;
  progress_total: number;
  error: string;
  created: number[];
  skipped_duplicate: string[];
  skipped_conflict: string[];
  failed: { cnr: string; error: string }[];
  /** CNR -> possible conflicts of interest found for that imported case. */
  conflicts: Record<string, ConflictHit[]>;
}

// ---------------------------------------------------------------------------
// The redesigned search (ADVOCATE_SEARCH_V2): profiles, per-court status, High Courts
// ---------------------------------------------------------------------------

/** How a stored row relates to the advocate's profile, decided when read. */
export type MatchStatus = "matched" | "check" | "excluded" | "other";

/** A result row as the redesigned search stores it: the old fields plus the
 * advocate cell as the court listed it, the court it came from, a case year
 * (High Courts) and the label computed against the profile. */
export interface AdvocateResultRow extends AdvocateSearchResult {
  match_status?: MatchStatus;
  match_label?: string;
  listed_advocate_name?: string;
  listed_advocates?: string[];
  dist_code?: string;
  dist_name?: string;
  complex_code?: string;
  complex_name?: string;
  case_year?: number | null;
  /** "bar_code": the portal matched the bar number itself. */
  match_source?: "bar_code";
}

export interface AdvocateSearchProfile {
  id: number;
  display_name: string;
  bar_codes: string[];
  name_forms: string[];
  excluded_names: string[];
  /** What goes to eCourts, from the same function the search uses. */
  queries: string[];
  query_count: number;
  query_warning: string;
  /** Spellings worth offering as dashed chips; never added on their own. */
  suggestions: string[];
  created_at: string;
  updated_at: string;
}

export interface AdvocateProfileInput {
  display_name: string;
  bar_codes?: string[];
  name_forms?: string[];
  excluded_names?: string[];
}

export interface AdvocateFeatures {
  v2: boolean;
  seconds_per_call: number;
}

export type CourtRunStatus = "pending" | "running" | "done" | "failed";

export interface CourtRun {
  id: number;
  dist_code: string;
  dist_name: string;
  complex_name: string;
  status: CourtRunStatus;
  attempts: number;
  error_code: string;
  /** Plain language: "Portal disconnected. 3 attempts." */
  reason: string;
  raw_count: number;
  matched_count: number;
  seconds: number | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface CourtGroup {
  dist_code: string;
  name: string;
  total: number;
  done: number;
  failed: number;
  running: number;
  runs: CourtRun[];
}

export interface CourtsStatus {
  job: {
    id: number;
    status: string;
    cancel_requested: boolean;
    created_at: string;
    started_at: string | null;
    is_retrying: boolean;
    retry_job_id: number | null;
    can_retry: boolean;
  };
  counts: { total: number; done: number; failed: number; running: number; pending: number; raw: number; matched: number };
  seconds_left: number | null;
  needs_attention: CourtRun[];
  groups: CourtGroup[];
  court_site_url: string;
}

export interface HighCourtInfo {
  code: string;
  name: string;
  state_code: string;
  registry_benches: { code: string; name: string }[];
  supported: boolean;
  support_note: string;
}

export interface HighCourtBench {
  code: string;
  name: string;
  default: boolean;
}

export interface StartSearchV2Request {
  profile_id: number;
  court_type: "district" | "high_court";
  state_code?: string;
  dist_codes?: string[];
  hc_court_code?: string;
  bench_codes?: string[];
  status_filter: "Pending" | "Disposed" | "Both";
  search_by: "names" | "bar_code";
  bar_code?: string;
}

export interface StartSearchV2Response {
  job_id: number;
  queries: string[];
  portal_calls_per_court: number;
  warning?: string;
}

export interface RetryCourtsResponse {
  job_id: number;
  parent_job_id: number;
  courts: number;
}
