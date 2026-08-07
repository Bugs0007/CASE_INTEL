import type { CourtType } from "./case";

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
}

export interface AdvocateSearchRequest {
  name_or_bar_code: string;
  court_type: CourtType;
  /** The user always picks a STATE; the backend fans out across every
   * district and court complex in it -- unless dist_code narrows it to
   * just one district (fast path for an advocate who mainly practices
   * in one place). */
  state_code: string;
  dist_code?: string;
  status_filter?: "Pending" | "Disposed" | "Both";
}

export type AdvocateSearchJobStatus = "queued" | "running" | "succeeded" | "failed";

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
  results: AdvocateSearchResult[];
  /** The real match count, which may exceed results.length. */
  results_total: number;
  results_truncated: boolean;
  failures: AdvocateSearchFailure[];
  districts_total: number | null;
  districts_status: Record<string, AdvocateSearchDistrictStatus>;
  complexes_searched: number | null;
}

export interface AdvocateSearchPreference {
  court_type: CourtType;
  /** { state_code } only -- district/complex are discovered server-side. */
  hierarchy_config: Record<string, string>;
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
}
