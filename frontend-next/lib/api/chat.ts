import { apiClient } from "./client";
import type { ChatRequest, ChatResponse, Conversation } from "@/types";

export const chatApi = {
  send: (data: ChatRequest) =>
    apiClient<ChatResponse>("/chat/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

export const conversationsApi = {
  list: (caseId?: number) =>
    apiClient<Conversation[]>("/conversations/", {
      params: { case_id: caseId },
    }),

  get: (id: number) => apiClient<Conversation>(`/conversations/${id}/`),

  delete: (id: number) =>
    apiClient<void>(`/conversations/${id}/`, { method: "DELETE" }),
};
