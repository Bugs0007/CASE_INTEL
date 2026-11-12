import type {
  CaseNote,
  DraftApproveRequest,
  DraftCreateRequest,
  DraftDetail,
  DraftOutput,
  DraftOutputRequest,
  DraftRevision,
  DraftRevisionCreateRequest,
  DraftSummary,
} from "@/types/draft";
import { apiBlob, apiClient } from "./client";

const BASE = "/case-assistant";

export const draftsApi = {
  list: (caseId: number) => apiClient<DraftSummary[]>(`${BASE}/drafts/`, { params: { case_id: caseId } }),

  /** Replaying the same client_request_id returns the same draft. */
  create: (data: DraftCreateRequest) =>
    apiClient<DraftDetail>(`${BASE}/drafts/`, { method: "POST", body: JSON.stringify(data) }),

  get: (id: number) => apiClient<DraftDetail>(`${BASE}/drafts/${id}/`),

  revision: (id: number, version: number) =>
    apiClient<DraftRevision>(`${BASE}/drafts/${id}/revisions/${version}/`),

  saveRevision: (id: number, data: DraftRevisionCreateRequest) =>
    apiClient<DraftDetail>(`${BASE}/drafts/${id}/revisions/`, { method: "POST", body: JSON.stringify(data) }),

  retry: (id: number) => apiClient<DraftDetail>(`${BASE}/drafts/${id}/retry/`, { method: "POST" }),

  approve: (id: number, data: DraftApproveRequest) =>
    apiClient<DraftDetail>(`${BASE}/drafts/${id}/approve/`, { method: "POST", body: JSON.stringify(data) }),

  createOutput: (id: number, data: DraftOutputRequest) =>
    apiClient<DraftOutput>(`${BASE}/drafts/${id}/outputs/`, { method: "POST", body: JSON.stringify(data) }),

  /** Authenticated binary: fetched with the token header, never linked. */
  downloadOutput: (outputId: number) => apiBlob(`${BASE}/outputs/${outputId}/download/`),
};

export const caseNotesApi = {
  list: (caseId: number) => apiClient<CaseNote[]>(`/cases/${caseId}/notes/`),
  remove: (id: number) => apiClient<void>(`/case-notes/${id}/`, { method: "DELETE" }),
};
