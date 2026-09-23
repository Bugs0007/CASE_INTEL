import { apiBlob, apiClient } from "./client";
import type {
  BillingPortfolio,
  Client,
  ClientInput,
  ClientMessage,
  ClientMessageKind,
  ClientMessageStatus,
  ClientMessageUpdateInput,
  Document,
  DocTemplateForCase,
  DocTemplateSummary,
  GenerateDocumentInput,
  LatestRefreshRun,
  RefreshRun,
  SendClientMessageResult,
  SentMessage,
} from "@/types";

export const clientsApi = {
  list: (search?: string) => apiClient<Client[]>("/clients/", { params: { search } }),

  create: (data: ClientInput) =>
    apiClient<Client>("/clients/", { method: "POST", body: JSON.stringify(data) }),

  update: (id: number, data: Partial<ClientInput>) =>
    apiClient<Client>(`/clients/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),

  delete: (id: number) => apiClient<void>(`/clients/${id}/`, { method: "DELETE" }),

  /** Outstanding-statement PDF. Fetched as a blob: the endpoint needs the
   * auth header, which a plain <a href> can't send. */
  statementPdf: (id: number) => apiBlob(`/clients/${id}/statement/pdf/`),
};

export const billingPortfolioApi = {
  get: () => apiClient<BillingPortfolio>("/billing/portfolio/"),
};

export interface ClientMessageFilters {
  status?: ClientMessageStatus;
  case_id?: number;
  kind?: ClientMessageKind;
}

export const clientMessagesApi = {
  list: (filters?: ClientMessageFilters) =>
    apiClient<ClientMessage[]>("/client-messages/", {
      params: { status: filters?.status, case_id: filters?.case_id, kind: filters?.kind },
    }),

  update: (id: number, data: ClientMessageUpdateInput) =>
    apiClient<ClientMessage>(`/client-messages/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  /** Discards the draft (kept server-side so it isn't generated again). */
  discard: (id: number) =>
    apiClient<ClientMessage>(`/client-messages/${id}/`, { method: "DELETE" }),

  /** Resolves (does not throw) with sent=false when the server has no
   * email credentials -- the message is logged instead. */
  send: (id: number) =>
    apiClient<SendClientMessageResult>(`/client-messages/${id}/send/`, { method: "POST" }),
};

export const sentMessagesApi = {
  list: (filters?: { case_id?: number; kind?: string }) =>
    apiClient<SentMessage[]>("/sent-messages/", {
      params: { case_id: filters?.case_id, kind: filters?.kind },
    }),
};

export const docTemplatesApi = {
  list: () => apiClient<DocTemplateSummary[]>("/doc-templates/"),

  forCase: (caseId: number, contactId?: number | null) =>
    apiClient<DocTemplateForCase[]>("/doc-templates/", {
      params: { case: caseId, contact: contactId ?? undefined },
    }),

  generate: (caseId: number, data: GenerateDocumentInput) =>
    apiClient<Document>(`/cases/${caseId}/generate-document/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export const refreshAllApi = {
  latest: () => apiClient<LatestRefreshRun>("/cases/refresh-all/"),
  start: () => apiClient<RefreshRun>("/cases/refresh-all/", { method: "POST" }),
  status: (jobId: number) => apiClient<RefreshRun>(`/cases/refresh-all/${jobId}/`),
  cancel: (jobId: number) =>
    apiClient<RefreshRun>(`/cases/refresh-all/${jobId}/cancel/`, { method: "POST" }),
};
