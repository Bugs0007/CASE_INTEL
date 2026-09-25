"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Laptop, Loader2, LogOut } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import { apiErrorDetail } from "@/lib/api/client";
import { authSessionsApi, type AuthSessionRow } from "@/lib/api/auth";
import { formatRelativeTime } from "@/lib/utils";

const sessionKeys = { all: ["auth-sessions"] as const };

/** "Chrome on Windows" from a user-agent string -- enough to recognise a
 * device, no parsing library. */
export function describeDevice(userAgent: string): string {
  const ua = userAgent || "";
  const browser = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Firefox\//.test(ua)
        ? "Firefox"
        : /Safari\//.test(ua)
          ? "Safari"
          : "";
  const os = /Windows/.test(ua)
    ? "Windows"
    : /Android/.test(ua)
      ? "Android"
      : /iPhone|iPad/.test(ua)
        ? "iOS"
        : /Mac OS X/.test(ua)
          ? "macOS"
          : /Linux/.test(ua)
            ? "Linux"
            : "";
  if (browser && os) return `${browser} on ${os}`;
  return browser || os || "Unknown device";
}

/** Every browser signed in to this account, each its own session: signing
 * out here (or logging out there) ends only that one. Sessions end by
 * themselves after a week without use. */
export function SignedInSessionsCard() {
  const queryClient = useQueryClient();
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: sessionKeys.all,
    queryFn: () => authSessionsApi.list(),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => authSessionsApi.revoke(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.all }),
  });
  const revokeOthers = useMutation({
    mutationFn: () => authSessionsApi.revokeOthers(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.all }),
  });
  const others = sessions.filter((s) => !s.current);

  async function handleRevoke(session: AuthSessionRow) {
    try {
      await revoke.mutateAsync(session.id);
      showToast.success("Signed out", `${describeDevice(session.user_agent)} is signed out.`);
    } catch (error) {
      showToast.error("Could not sign that device out", apiErrorDetail(error, "Please try again."));
    }
  }

  async function handleRevokeOthers() {
    try {
      const { revoked } = await revokeOthers.mutateAsync();
      showToast.success("Other devices signed out", `${revoked} session${revoked === 1 ? "" : "s"} ended.`);
    } catch (error) {
      showToast.error("Could not sign the other devices out", apiErrorDetail(error, "Please try again."));
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <Laptop className="h-5 w-5 text-gray-500" />
          Signed-in devices
        </CardTitle>
        {others.length > 0 && (
          <Button variant="secondary" size="sm" onClick={handleRevokeOthers} disabled={revokeOthers.isPending}>
            {revokeOthers.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
            Sign out all other devices
          </Button>
        )}
      </CardHeader>
      <CardContent>
        <p className="mb-3 text-sm text-gray-600">
          Each sign-in is separate: logging out on one device doesn&apos;t sign the others out. A device
          that isn&apos;t used for 7 days is signed out automatically.
        </p>
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : (
          <ul className="divide-y divide-gray-100 rounded-lg border border-gray-100">
            {sessions.map((session) => (
              <li key={session.id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-gray-900">
                    {describeDevice(session.user_agent)}
                    {session.current && <span className="ml-2 ci-chip ci-chip--ok align-middle">This device</span>}
                  </div>
                  <div className="text-xs text-gray-500">
                    Active {formatRelativeTime(session.last_used_at)}
                    {session.ip_address ? ` · ${session.ip_address}` : ""} · {session.source_display}
                  </div>
                </div>
                {!session.current && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRevoke(session)}
                    disabled={revoke.isPending && revoke.variables === session.id}
                    aria-label={`Sign out ${describeDevice(session.user_agent)}`}
                  >
                    Sign out
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
