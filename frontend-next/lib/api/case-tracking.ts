import { apiClient } from "./client";
import type {
  Case,
  CourtStructureResponse,
  CourtType,
  TrackingConfig,
  TrackingPreview,
  TrackingResponse,
} from "@/types";

export const caseTrackingApi = {
  courtStructure: (params: {
    court_type: CourtType;
    state_code?: string;
    dist_code?: string;
    court_complex_code?: string;
    est_code?: string;
    hc_court_code?: string;
    bench_code?: string;
  }) =>
    apiClient<CourtStructureResponse>("/court-structure/", {
      params: params as Record<string, string | undefined>,
    }),

  /** Fetches live court data WITHOUT persisting it -- returns a preview
   * plus a preview_token to pass to confirm(). Nothing is saved until
   * confirm() is called with that token. */
  preview: (caseId: number, config: TrackingConfig) =>
    apiClient<TrackingPreview>(`/cases/${caseId}/tracking/preview/`, {
      method: "POST",
      body: JSON.stringify(config),
    }),

  /** Persists a previously-previewed fetch. */
  confirm: (caseId: number, previewToken: string) =>
    apiClient<TrackingResponse>(`/cases/${caseId}/tracking/confirm/`, {
      method: "POST",
      body: JSON.stringify({ preview_token: previewToken }),
    }),

  refresh: (caseId: number, force = false) =>
    apiClient<TrackingResponse>(`/cases/${caseId}/tracking/refresh/`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),

  /** Clears all tracking state for a case (CNR, config, hearings sourced
   * from eCourts) -- the recovery path when setup was confirmed against
   * the wrong case. */
  untrack: (caseId: number) =>
    apiClient<Case>(`/cases/${caseId}/tracking/`, {
      method: "DELETE",
    }),
};
