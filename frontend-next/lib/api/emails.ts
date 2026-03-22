import { apiClient } from "./client";
import type { Email } from "@/types";

interface EmailFilters {
  case_id?: number;
  unlinked?: boolean;
}

export const emailsApi = {
  list: (filters?: EmailFilters) =>
    apiClient<Email[]>("/emails/", {
      params: {
        case_id: filters?.case_id,
        unlinked: filters?.unlinked ? "true" : undefined,
      },
    }),

  link: (id: number, caseId: number) =>
    apiClient<{ message: string; case_id: number }>(`/emails/${id}/link/`, {
      method: "POST",
      body: JSON.stringify({ case_id: caseId }),
    }),
};
