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
  /** The user picks only a STATE; the backend fans out across every
   * district and court complex in it. */
  state_code: string;
  status_filter?: "Pending" | "Disposed" | "Both";
}

export type AdvocateSearchJobStatus = "queued" | "running" | "succeeded" | "failed";

/** One court complex that was skipped during the state-wide fan-out
 * (CAPTCHA/portal error). court_complex is null when the district's
 * complex-list call itself failed. */
export interface AdvocateSearchFailure {
  district: string;
  court_complex: string | null;
  error: string;
}

/** POST /api/cases/search-advocate/ enqueues a job and returns its id. */
export interface AdvocateSearchStartResponse {
  job_id: number;
}

/** GET /api/cases/search-advocate/<job_id>/ -- progress is
 * districts_done / total_districts while running. */
export interface AdvocateSearchJobResult {
  status: AdvocateSearchJobStatus;
  progress_current: number;
  progress_total: number;
  error: string;
  results: AdvocateSearchResult[];
  failures: AdvocateSearchFailure[];
  districts_total: number | null;
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
