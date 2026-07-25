import { apiClient } from "./client";
import type {
  AdvocateImportJobResult,
  AdvocateImportSelection,
  AdvocateImportStartResponse,
  AdvocateSearchJobResult,
  AdvocateSearchPreference,
  AdvocateSearchRequest,
  AdvocateSearchStartResponse,
  CourtType,
} from "@/types";

export const advocateSearchApi = {
  /** Enqueues the state-wide fan-out search -- async, poll
   * getSearchStatus(job_id) for progress and results. */
  search: (body: AdvocateSearchRequest) =>
    apiClient<AdvocateSearchStartResponse>("/cases/search-advocate/", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  getSearchStatus: (jobId: number) =>
    apiClient<AdvocateSearchJobResult>(`/cases/search-advocate/${jobId}/`),

  /** Re-runs only the districts that didn't fully succeed in `jobId`,
   * carrying its already-collected results forward. Returns a NEW job id
   * to poll with getSearchStatus. */
  retryFailedDistricts: (jobId: number) =>
    apiClient<AdvocateSearchStartResponse>(`/cases/search-advocate/${jobId}/retry-failed/`, {
      method: "POST",
    }),

  /** Enqueues the sequential, 1s-delayed fetch of each selected case --
   * async, poll getImportStatus(job_id) for the outcome. searchJobId, when
   * given, identifies the advocate_search job these results came from --
   * the backend pulls the advocate_name/bar_code that was searched with
   * off it for user_party_role auto-detection (see
   * AdvocateSearchImportView). Omit if unavailable; auto-detection is
   * simply skipped for that batch. */
  startImport: (courtType: CourtType, selected: AdvocateImportSelection[], searchJobId?: number) =>
    apiClient<AdvocateImportStartResponse>("/cases/search-advocate/import/", {
      method: "POST",
      body: JSON.stringify({ court_type: courtType, selected, search_job_id: searchJobId }),
    }),

  getImportStatus: (jobId: number) =>
    apiClient<AdvocateImportJobResult>(`/cases/search-advocate/import/${jobId}/`),

  getPreference: () =>
    apiClient<AdvocateSearchPreference | null>("/cases/search-advocate/preference/"),
};
