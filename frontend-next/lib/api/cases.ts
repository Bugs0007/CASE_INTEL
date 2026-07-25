import { apiClient } from "./client";
import type { Case, CaseUpdateInput, CaseStatus } from "@/types";

export const casesApi = {
  list: (status?: CaseStatus, since?: string) =>
    apiClient<Case[]>("/cases/", { params: { status, since } }),

  get: (id: number) => apiClient<Case>(`/cases/${id}/`),

  update: (id: number, data: CaseUpdateInput) =>
    apiClient<Case>(`/cases/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    apiClient<void>(`/cases/${id}/`, { method: "DELETE" }),
};
