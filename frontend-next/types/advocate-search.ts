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
  hierarchy_config: Record<string, string>;
  status_filter?: "Pending" | "Disposed" | "Both";
}

export interface AdvocateSearchResponse {
  results: AdvocateSearchResult[];
}

export interface AdvocateSearchPreference {
  court_type: CourtType;
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
