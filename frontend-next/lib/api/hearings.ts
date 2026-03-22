import { apiClient } from "./client";
import type {
  Hearing,
  HearingCreateInput,
  HearingUpdateInput,
  HearingStatus,
} from "@/types";

interface HearingFilters {
  case_id?: number;
  status?: HearingStatus;
  upcoming?: boolean;
  past?: boolean;
}

export const hearingsApi = {
  list: (filters?: HearingFilters) =>
    apiClient<Hearing[]>("/hearings/", {
      params: {
        case_id: filters?.case_id,
        status: filters?.status,
        upcoming: filters?.upcoming ? "true" : undefined,
        past: filters?.past ? "true" : undefined,
      },
    }),

  get: (id: number) => apiClient<Hearing>(`/hearings/${id}/`),

  create: (data: HearingCreateInput) =>
    apiClient<Hearing>("/hearings/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: HearingUpdateInput) =>
    apiClient<Hearing>(`/hearings/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    apiClient<void>(`/hearings/${id}/`, { method: "DELETE" }),
};
