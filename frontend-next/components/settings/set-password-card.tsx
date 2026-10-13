"use client";

import { useState } from "react";
import { AlertTriangle, KeyRound, Loader2, Save } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showToast } from "@/components/ui/toaster";
import { APIError } from "@/lib/api/client";
import { googleAccountApi } from "@/lib/api/auth";

function errorText(error: unknown): string {
  if (error instanceof APIError && error.data && typeof error.data === "object") {
    const data = error.data as Record<string, unknown>;
    if (typeof data.detail === "string") return data.detail;
    const field = data.new_password;
    if (Array.isArray(field) && field[0]) return String(field[0]);
  }
  return "Something went wrong. Please try again.";
}

/** Shown instead of "Change Password" for an account with no password (a
 * Google-only signup). Setting one lets the account change its username too,
 * since that asks for the current password. */
export function SetPasswordCard({ onDone }: { onDone: () => void }) {
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  const matches = confirmPassword.length === 0 || newPassword === confirmPassword;
  const canSubmit = newPassword.length > 0 && newPassword === confirmPassword;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!canSubmit) return;
    setIsPending(true);
    try {
      await googleAccountApi.setPassword(newPassword);
      showToast.success("Password set", "You can now sign in with your username and password too.");
      setNewPassword("");
      setConfirmPassword("");
      onDone();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setIsPending(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-gray-500" />
          Set a password
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4 text-sm text-gray-600">
          You signed up with Google, so this account has no password yet. Set one to also sign in
          with your username, and to change your username later.
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label htmlFor="set_password_new" className="mb-1 block text-sm font-medium text-gray-700">
                New Password
              </label>
              <Input
                id="set_password_new"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="set_password_confirm" className="mb-1 block text-sm font-medium text-gray-700">
                Confirm Password
              </label>
              <Input
                id="set_password_confirm"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
              {!matches && <p className="mt-1 text-xs text-status-alert">Passwords don&apos;t match.</p>}
            </div>
          </div>
          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-status-alert-soft p-3 text-sm text-status-alert">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}
          <Button type="submit" disabled={!canSubmit || isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {isPending ? "Saving..." : "Set Password"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
