import { apiClient } from "./client";
import type {
  Case,
  CaseCreateInput,
  CaseUpdateInput,
  CaseStatus,
} from "@/types";

export const casesApi = {
  list: (status?: CaseStatus) =>
    apiClient<Case[]>("/cases/", { params: { status } }),

  get: (id: number) => apiClient<Case>(`/cases/${id}/`),

  create: (data: CaseCreateInput) =>
    apiClient<Case>("/cases/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: CaseUpdateInput) =>
    apiClient<Case>(`/cases/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    apiClient<void>(`/cases/${id}/`, { method: "DELETE" }),
};
