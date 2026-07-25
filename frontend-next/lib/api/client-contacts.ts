import { apiClient } from "./client";
import type { ClientContact, ClientContactInput } from "@/types";

export const clientContactsApi = {
  list: (caseId: number) =>
    apiClient<ClientContact[]>("/client-contacts/", { params: { case_id: caseId } }),

  create: (data: ClientContactInput) =>
    apiClient<ClientContact>("/client-contacts/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: Partial<ClientContactInput>) =>
    apiClient<ClientContact>(`/client-contacts/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (id: number) =>
    apiClient<void>(`/client-contacts/${id}/`, { method: "DELETE" }),
};
