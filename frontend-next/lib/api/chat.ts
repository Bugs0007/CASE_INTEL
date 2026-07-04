import { API_BASE_URL, APIError, apiClient } from "./client";
import type {
  ChatRequest,
  ChatResponse,
  Conversation,
  ConversationExportFormat,
  Message,
} from "@/types";

function getDownloadFilename(
  disposition: string | null,
  fallback: string,
): string {
  const match = disposition?.match(/filename="?([^"]+)"?/i);
  return match?.[1] || fallback;
}

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

  getMessages: (id: number) =>
    apiClient<Message[]>(`/conversations/${id}/messages/`),

  export: async (id: number, format: ConversationExportFormat) => {
    const url = new URL(`${API_BASE_URL}/conversations/${id}/export/`);
    url.searchParams.set("format", format);

    const response = await fetch(url.toString());
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new APIError(response.status, data);
    }

    return {
      blob: await response.blob(),
      filename: getDownloadFilename(
        response.headers.get("Content-Disposition"),
        `conversation.${format}`,
      ),
    };
  },

  delete: (id: number) =>
    apiClient<void>(`/conversations/${id}/`, { method: "DELETE" }),
};
