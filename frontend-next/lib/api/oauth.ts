import { apiClient } from "./client";

/** One app connected to this account through the MCP connector (OAuth),
 * e.g. Claude. GET /api/oauth/connected-apps/. */
export interface ConnectedAppRow {
  id: number;
  name: string;
  /** "cimd" (Claude's published identity), "dcr" (registered itself) or "manual". */
  registration_source: string;
  scopes: string[];
  connected_at: string;
  last_active_at: string;
}

/** One MCP tool call on this account. GET /api/oauth/activity/. */
export interface McpActivityRow {
  id: number;
  created_at: string;
  kind: "read" | "write";
  tool: string;
  result: "ok" | "error" | "denied" | "rate_limited" | string;
  case_id: number | null;
  case_title: string | null;
  app_name: string | null;
  proposal_id: number | null;
}

export const connectedAppsApi = {
  list: () => apiClient<{ results: ConnectedAppRow[] }>("/oauth/connected-apps/").then((r) => r.results),
  revoke: (id: number) => apiClient<void>(`/oauth/connected-apps/${id}/`, { method: "DELETE" }),
  activity: () => apiClient<{ results: McpActivityRow[] }>("/oauth/activity/").then((r) => r.results),
};
