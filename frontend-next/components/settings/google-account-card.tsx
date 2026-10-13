"use client";

import { useState } from "react";
import { Link2, Loader2, Unplug } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import { GoogleSignInButton } from "@/components/auth/google-sign-in";
import { googleAccountApi, type AuthMe } from "@/lib/api/auth";
import { GOOGLE_CLIENT_ID, googleErrorMessage } from "@/lib/google-auth";

interface GoogleAccountCardProps {
  me: AuthMe;
  /** Re-read /auth/me/ after a connect or disconnect. */
  onChanged: () => void;
  /** Whether this deployment has a Google client id (defaults to the env var). */
  configured?: boolean;
}

/** Connect or disconnect the Google account used for "Continue with Google".
 *
 * Hidden entirely on a credentials-locked account (the shared demo login:
 * connecting Google there would hand the account to whoever clicks first;
 * the server refuses it too). Disconnect is disabled while the account has
 * no password -- it would be left with no way to sign in. */
export function GoogleAccountCard({
  me,
  onChanged,
  configured = Boolean(GOOGLE_CLIENT_ID),
}: GoogleAccountCardProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (me.credentials_locked) return null;
  // Nothing to connect and nothing connected: don't show a dead card.
  if (!me.google_linked && !configured) return null;

  async function connect(credential: string) {
    setError(null);
    setBusy(true);
    try {
      const result = await googleAccountApi.link(credential);
      showToast.success("Google connected", `You can now sign in with ${result.google_email}.`);
      onChanged();
    } catch (err) {
      setError(googleErrorMessage(err).message || "Could not connect Google.");
    } finally {
      setBusy(false);
    }
  }

  async function disconnect() {
    setError(null);
    setBusy(true);
    try {
      await googleAccountApi.unlink();
      showToast.success("Google disconnected", "You'll sign in with your username and password.");
      onChanged();
    } catch (err) {
      setError(googleErrorMessage(err).message || "Could not disconnect Google.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Link2 className="h-5 w-5 text-gray-500" />
          Google account
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {me.google_linked ? (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-sm text-gray-700">
                Connected as <span className="font-medium text-gray-900">{me.google_email}</span>
              </p>
              <Button variant="secondary" size="sm" onClick={disconnect} disabled={busy || !me.has_password}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Unplug className="h-4 w-4" />}
                Disconnect
              </Button>
            </div>
            {!me.has_password && (
              <p className="text-xs text-gray-500">
                Set a password first. Without one you couldn&apos;t sign in after disconnecting Google.
              </p>
            )}
          </>
        ) : (
          <>
            <p className="text-sm text-gray-600">
              Connect a Google account to sign in with one click. It can only be connected to this
              account.
            </p>
            <GoogleSignInButton
              onCredential={connect}
              onError={() => setError("Google sign-in didn't go through. Try again.")}
            />
          </>
        )}
        {error && (
          <div role="alert" className="rounded-lg bg-status-alert-soft p-3 text-sm text-status-alert">
            {error}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
