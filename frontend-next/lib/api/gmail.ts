import { apiClient } from "./client";
import type { GmailStatus, SyncConfig, SyncResult } from "@/types";

export const gmailApi = {
  getStatus: () => apiClient<GmailStatus>("/gmail/status/"),

  auth: () => apiClient<{ auth_url: string }>("/gmail/auth/"),

  callback: (code: string) =>
    apiClient<{ success: boolean }>("/gmail/callback/", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),

  sync: (config?: SyncConfig) =>
    apiClient<SyncResult>("/gmail/sync/", {
      method: "POST",
      body: JSON.stringify(config || {}),
    }),

  disconnect: () =>
    apiClient<{ success: boolean }>("/gmail/disconnect/", {
      method: "POST",
    }),
};
