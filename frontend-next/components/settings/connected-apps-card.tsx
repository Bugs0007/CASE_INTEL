"use client";

/* Connected apps (MCP connector) and recent Claude activity.
 *
 * Built to match the existing "Signed-in devices" card. No design reference
 * was supplied for this screen (docs/MCP_PLAN.md Phase 2): it needs one
 * before launch. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import { apiErrorDetail } from "@/lib/api/client";
import { connectedAppsApi, type ConnectedAppRow, type McpActivityRow } from "@/lib/api/oauth";
import { formatRelativeTime } from "@/lib/utils";

const keys = {
  apps: ["oauth-connected-apps"] as const,
  activity: ["oauth-activity"] as const,
};

const SCOPE_LABELS: Record<string, string> = {
  "cases:read": "Read case data",
  "cases:write": "Propose and confirm changes",
};

/** "get_last_order" -> "Get last order". */
export function toolLabel(tool: string): string {
  const words = tool.replace(/_/g, " ").trim();
  return words ? words[0].toUpperCase() + words.slice(1) : "Unknown tool";
}

const RESULT_LABELS: Record<string, string> = {
  ok: "Done",
  error: "Failed",
  denied: "Not allowed",
  rate_limited: "Too many calls",
};

export function ConnectedAppsCard() {
  const queryClient = useQueryClient();
  const { data: apps = [], isLoading } = useQuery({ queryKey: keys.apps, queryFn: () => connectedAppsApi.list() });
  const { data: activity = [], isLoading: activityLoading } = useQuery({
    queryKey: keys.activity,
    queryFn: () => connectedAppsApi.activity(),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => connectedAppsApi.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.apps });
      queryClient.invalidateQueries({ queryKey: keys.activity });
    },
  });

  async function handleRevoke(app: ConnectedAppRow) {
    if (!window.confirm(`Remove ${app.name}'s access to your Case Intel account? It must sign in again to reconnect.`)) {
      return;
    }
    try {
      await revoke.mutateAsync(app.id);
      showToast.success("Access removed", `${app.name} can no longer reach your account.`);
    } catch (error) {
      showToast.error("Could not remove access", apiErrorDetail(error, "Please try again."));
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bot className="h-5 w-5 text-gray-500" aria-hidden="true" />
          Connected apps
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-gray-600">
          Apps such as Claude that you allowed to use your Case Intel account. They can read your case data and
          propose changes that you confirm. They cannot send email, create invoices, delete anything or fetch from
          eCourts.
        </p>
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Loading…
          </div>
        ) : apps.length === 0 ? (
          <p className="text-sm text-gray-500">No apps are connected.</p>
        ) : (
          <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
            {apps.map((app) => (
              <li key={app.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-900">{app.name}</div>
                  <div className="text-xs text-gray-500">
                    {app.scopes.map((s) => SCOPE_LABELS[s] ?? s).join(" · ")} · Connected{" "}
                    {formatRelativeTime(app.connected_at)} · Last active {formatRelativeTime(app.last_active_at)}
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleRevoke(app)}
                  disabled={revoke.isPending && revoke.variables === app.id}
                  aria-label={`Remove access for ${app.name}`}
                >
                  Remove access
                </Button>
              </li>
            ))}
          </ul>
        )}

        <h3 className="mb-2 mt-6 text-sm font-semibold text-gray-900">Recent Claude activity</h3>
        {activityLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500" role="status">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Loading…
          </div>
        ) : activity.length === 0 ? (
          <p className="text-sm text-gray-500">No activity yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
            {activity.map((row: McpActivityRow) => (
              <li key={row.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                <div className="min-w-0 text-sm text-gray-900">
                  {toolLabel(row.tool)}
                  {row.case_title && <span className="text-gray-500"> · {row.case_title}</span>}
                  {row.kind === "write" && <span className="ml-2 ci-chip align-middle">Change</span>}
                </div>
                <div className="text-xs text-gray-500">
                  {RESULT_LABELS[row.result] ?? row.result} · {formatRelativeTime(row.created_at)}
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
