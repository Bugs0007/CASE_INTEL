import { apiClient } from "./client";
import type { CaseEvent, CaseEventFilters, CaseEventInput } from "@/types";

export const caseEventsApi = {
  list: (filters: CaseEventFilters = {}) =>
    apiClient<CaseEvent[]>("/case-events/", { params: { ...filters } }),

  create: (data: CaseEventInput) =>
    apiClient<CaseEvent>("/case-events/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: Partial<CaseEventInput>) =>
    apiClient<CaseEvent>(`/case-events/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: number) => apiClient<void>(`/case-events/${id}/`, { method: "DELETE" }),
};
