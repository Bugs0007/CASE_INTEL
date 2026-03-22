import { apiClient } from "./client";
import type { GmailStatus, SyncConfig, SyncResult } from "@/types";

export const gmailApi = {
  status: () => apiClient<GmailStatus>("/gmail/status/"),

  auth: () => apiClient<{ auth_url: string }>("/gmail/auth/"),

  sync: (config?: SyncConfig) =>
    apiClient<SyncResult>("/gmail/sync/", {
      method: "POST",
      body: JSON.stringify(config || {}),
    }),
};
