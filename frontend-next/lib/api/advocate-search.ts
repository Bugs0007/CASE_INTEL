import { apiClient } from "./client";
import type {
  AdvocateFeatures,
  AdvocateImportJobResult,
  AdvocateImportSelection,
  AdvocateImportStartResponse,
  AdvocateProfileInput,
  AdvocateSearchJobResult,
  AdvocateSearchPreference,
  AdvocateSearchProfile,
  AdvocateSearchRequest,
  AdvocateSearchStartResponse,
  CourtsStatus,
  CourtType,
  HighCourtBench,
  HighCourtInfo,
  RetryCourtsResponse,
  StartSearchV2Request,
  StartSearchV2Response,
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

  /** The last-used state and districts. With a name and state, also says
   * whether a Quick search is available for them (quick_search). */
  getPreference: (query?: { nameOrBarCode: string; stateCode: string }) =>
    apiClient<AdvocateSearchPreference | null>("/cases/search-advocate/preference/", {
      params: query
        ? { name_or_bar_code: query.nameOrBarCode, state_code: query.stateCode }
        : undefined,
    }),

  // -- The redesigned search (ADVOCATE_SEARCH_V2) ---------------------------

  /** Whether the redesigned search is switched on, and the per-request time estimate. */
  features: () => apiClient<AdvocateFeatures>("/advocate-search/features/"),

  listProfiles: () => apiClient<AdvocateSearchProfile[]>("/advocate-profiles/"),
  createProfile: (body: AdvocateProfileInput) =>
    apiClient<AdvocateSearchProfile>("/advocate-profiles/", { method: "POST", body: JSON.stringify(body) }),
  updateProfile: (id: number, body: Partial<AdvocateProfileInput>) =>
    apiClient<AdvocateSearchProfile>(`/advocate-profiles/${id}/`, { method: "PATCH", body: JSON.stringify(body) }),
  /** "Not me": rejects the name from every search. Moves it off the name forms. */
  excludeName: (id: number, name: string) =>
    apiClient<AdvocateSearchProfile>(`/advocate-profiles/${id}/exclude/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  /** "That's me": the spelling is the advocate's own. Moves it off the Not me list. */
  addNameForm: (id: number, name: string) =>
    apiClient<AdvocateSearchProfile>(`/advocate-profiles/${id}/add-name-form/`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  searchV2: (body: StartSearchV2Request) =>
    apiClient<StartSearchV2Response>("/cases/search-advocate/", { method: "POST", body: JSON.stringify(body) }),
  /** Court-by-court status of a redesigned search. */
  getCourts: (jobId: number) => apiClient<CourtsStatus>(`/cases/search-advocate/${jobId}/courts/`),
  /** Search only the failed courts (or chosen ones) again; merges into the same list. */
  retryCourts: (jobId: number, body: { only_failed: true } | { complex_ids: number[] }) =>
    apiClient<RetryCourtsResponse>(`/cases/search-advocate/${jobId}/retry/`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  cancelSearch: (jobId: number) =>
    apiClient<{ status: string; cancel_requested: boolean }>(`/cases/search-advocate/${jobId}/cancel/`, {
      method: "POST",
    }),
  /** The caller's own queued/running searches, so a refreshed page can pick one up again. */
  listActive: () =>
    apiClient<{ job_id: number; status: string; state_code: string }[]>("/cases/search-advocate/active/"),

  listHighCourts: () => apiClient<{ courts: HighCourtInfo[] }>("/cases/high-courts/"),
  highCourtBenches: (code: string) =>
    apiClient<{ court: HighCourtInfo; benches: HighCourtBench[] }>(`/cases/high-courts/${code}/benches/`),
};
