"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { storeSession } from "@/lib/auth";
import { googleLogin, register, validateInvite, type InviteValidation } from "@/lib/api/auth";
import { APIError } from "@/lib/api/client";
import { GOOGLE_CLIENT_ID, googleErrorMessage } from "@/lib/google-auth";
import { GoogleSignInButton, OrDivider } from "@/components/auth/google-sign-in";

type InviteState =
  | { status: "checking" }
  | { status: "invalid"; reason: InviteValidation["reason"] }
  | { status: "valid" };

/** Shown when there is no (usable) invite link. Creating an account with
 * Google needs no invite while sign-up is open; the password form below only
 * exists behind an invite link. */
function NoInviteCard({
  reason,
  googleButton,
}: {
  reason: InviteValidation["reason"];
  googleButton: React.ReactNode;
}) {
  const inviteProblem =
    reason === "used"
      ? "That invite link has already been used."
      : reason === "expired"
        ? "That invite link has expired."
        : reason === "not_found"
          ? "That invite link isn't valid."
          : null;

  return (
    <div className="ci-card p-8">
      {googleButton}
      <p className="text-center text-sm text-gray-600 leading-relaxed" style={{ marginTop: googleButton ? 18 : 0 }}>
        {inviteProblem ? `${inviteProblem} ` : ""}
        Have an invite link? Open it to sign up with a username and password.
      </p>
    </div>
  );
}

export function RegisterClient() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [invite, setInvite] = useState<InviteState>(
    token ? { status: "checking" } : { status: "invalid", reason: null },
  );

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [googleHidden, setGoogleHidden] = useState(false);
  const showGoogle = Boolean(GOOGLE_CLIENT_ID) && !googleHidden;

  useEffect(() => {
    if (!token) return;
    let cancelled = false;

    validateInvite(token)
      .then((result) => {
        if (cancelled) return;
        if (result.valid) {
          setInvite({ status: "valid" });
          if (result.email) setEmail(result.email);
        } else {
          setInvite({ status: "invalid", reason: result.reason });
        }
      })
      .catch(() => {
        if (!cancelled) setInvite({ status: "invalid", reason: null });
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirmPassword) {
      setError("Passwords don't match.");
      return;
    }

    setLoading(true);
    try {
      storeSession(await register(token, username, password, email));
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof APIError && err.data && typeof err.data === "object") {
        const fieldErrors = Object.values(err.data as Record<string, unknown>)
          .flat()
          .join(" ");
        setError(fieldErrors || "Could not create your account.");
      } else {
        setError("Could not reach the server. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleGoogle(credential: string) {
    setError(null);
    setLoading(true);
    try {
      // A valid invite link rides along so the invite is spent on this account.
      storeSession(await googleLogin(credential, invite.status === "valid" ? token : undefined));
      router.push("/dashboard");
    } catch (err) {
      const result = googleErrorMessage(err);
      if (result.hideButton) setGoogleHidden(true);
      else setError(result.message);
    } finally {
      setLoading(false);
    }
  }

  const googleButton = showGoogle ? (
    <GoogleSignInButton
      text="signup_with"
      onCredential={handleGoogle}
      onError={() => setError("Google sign-in didn't go through. Try again.")}
    />
  ) : null;

  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="w-[400px] max-w-[calc(100vw-40px)]">
        <div className="text-center mb-7">
          <div className="font-serif text-[26px] text-gray-900">Case Intel</div>
          <div className="text-sm text-gray-500 mt-1.5">
            {invite.status === "valid" ? "Create your workspace" : "Create your account"}
          </div>
        </div>

        {invite.status === "checking" && (
          <div className="ci-card p-8 text-center text-sm text-gray-500">Checking your invite link…</div>
        )}

        {invite.status === "invalid" && (
          <>
            <NoInviteCard reason={invite.reason} googleButton={googleButton} />
            {error && <div className="ci-error bg-status-alert-soft rounded px-3 py-2.5 mt-3">{error}</div>}
          </>
        )}

        {invite.status === "valid" && (
          <div className="ci-card p-8">
            {googleButton && (
              <>
                {googleButton}
                <OrDivider />
              </>
            )}
            <form onSubmit={handleSubmit} className="flex flex-col gap-[18px]">
              <div>
                <label htmlFor="username" className="ci-label">
                  Username
                </label>
                <input
                  id="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  placeholder="advocate@caseintel.com"
                  required
                  className="ci-input"
                />
              </div>
              <div>
                <label htmlFor="email" className="ci-label">
                  Email (optional)
                </label>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  placeholder="you@example.com"
                  className="ci-input"
                />
              </div>
              <div>
                <label htmlFor="password" className="ci-label">
                  Password
                </label>
                <div className="relative">
                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    placeholder="••••••••"
                    required
                    className="ci-input pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                    tabIndex={-1}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>
              <div>
                <label htmlFor="confirm-password" className="ci-label">
                  Re-enter password
                </label>
                <div className="relative">
                  <input
                    id="confirm-password"
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    placeholder="••••••••"
                    required
                    className="ci-input pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword((v) => !v)}
                    aria-label={showConfirmPassword ? "Hide password" : "Show password"}
                    aria-pressed={showConfirmPassword}
                    tabIndex={-1}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                  >
                    {showConfirmPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>
              {error && <div className="ci-error bg-status-alert-soft rounded px-3 py-2.5 mt-0">{error}</div>}
              <button type="submit" disabled={loading} className="ci-btn ci-btn--solid w-full justify-center">
                {loading ? "Creating account..." : "Create Account"}
              </button>
            </form>
          </div>
        )}

        <div className="text-center mt-[18px] text-[13px] text-gray-400">
          Already have an account?{" "}
          <Link href="/login" className="text-accent font-semibold hover:underline">
            Sign in
          </Link>
          <div className="mt-2">
            <Link href="/privacy" className="hover:underline">
              Privacy
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
