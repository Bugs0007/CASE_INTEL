import { apiClient } from "./client";
import type {
  AdvocateImportJobResult,
  AdvocateImportSelection,
  AdvocateImportStartResponse,
  AdvocateSearchPreference,
  AdvocateSearchRequest,
  AdvocateSearchResponse,
  CourtType,
} from "@/types";

export const advocateSearchApi = {
  search: (body: AdvocateSearchRequest) =>
    apiClient<AdvocateSearchResponse>("/cases/search-advocate/", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Enqueues the sequential, 1s-delayed fetch of each selected case --
   * async, poll getImportStatus(job_id) for the outcome. */
  startImport: (courtType: CourtType, selected: AdvocateImportSelection[]) =>
    apiClient<AdvocateImportStartResponse>("/cases/search-advocate/import/", {
      method: "POST",
      body: JSON.stringify({ court_type: courtType, selected }),
    }),

  getImportStatus: (jobId: number) =>
    apiClient<AdvocateImportJobResult>(`/cases/search-advocate/import/${jobId}/`),

  getPreference: () =>
    apiClient<AdvocateSearchPreference | null>("/cases/search-advocate/preference/"),
};
