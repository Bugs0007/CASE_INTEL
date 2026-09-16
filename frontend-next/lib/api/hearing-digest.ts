import { apiBlob, apiClient } from "./client";
import type { CaseBriefingState, HearingDigest } from "@/types";

export const hearingDigestApi = {
  get: (hearingId: number) => apiClient<HearingDigest>(`/hearings/${hearingId}/digest/`),

  /** Queues the "state of the matter" paragraph if it is missing or out of
   * date; returns the resulting state either way. */
  requestBriefing: (hearingId: number) =>
    apiClient<CaseBriefingState>(`/hearings/${hearingId}/digest/briefing/`, { method: "POST" }),

  fetchPdf: (hearingId: number) => apiBlob(`/hearings/${hearingId}/digest/pdf/`),
};
