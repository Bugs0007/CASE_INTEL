import { apiClient } from "./client";
import type {
  CourtStructureResponse,
  CourtType,
  TrackingConfig,
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

  setup: (caseId: number, config: TrackingConfig) =>
    apiClient<TrackingResponse>(`/cases/${caseId}/tracking/`, {
      method: "POST",
      body: JSON.stringify(config),
    }),

  refresh: (caseId: number, force = false) =>
    apiClient<TrackingResponse>(`/cases/${caseId}/tracking/refresh/`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
};
