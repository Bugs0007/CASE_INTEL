"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { setToken, setUsername as storeUsername } from "@/lib/auth";
import { register, validateInvite, type InviteValidation } from "@/lib/api/auth";
import { APIError } from "@/lib/api/client";

type InviteState =
  | { status: "checking" }
  | { status: "invalid"; reason: InviteValidation["reason"] }
  | { status: "valid" };

function InviteOnlyNotice({ reason }: { reason: InviteValidation["reason"] }) {
  const message =
    reason === "used"
      ? "This invite link has already been used."
      : reason === "expired"
        ? "This invite link has expired."
        : "Case Intel is open to a small set of practices right now.";

  return (
    <div className="ci-card p-8 text-center">
      <p className="text-sm text-gray-600 leading-relaxed">
        {message} To request access, email{" "}
        <a href="mailto:samallabhagath@gmail.com" className="text-accent font-semibold hover:underline">
          samallabhagath@gmail.com
        </a>{" "}
        and you&apos;ll be sent an account once approved.
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
      const data = await register(token, username, password, email);
      setToken(data.token);
      storeUsername(data.username);
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

  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="w-[400px] max-w-[calc(100vw-40px)]">
        <div className="text-center mb-7">
          <div className="font-serif text-[26px] text-gray-900">Case Intel</div>
          <div className="text-sm text-gray-500 mt-1.5">
            {invite.status === "valid" ? "Create your workspace" : "Access is by invitation"}
          </div>
        </div>

        {invite.status === "checking" && (
          <div className="ci-card p-8 text-center text-sm text-gray-500">Checking your invite link…</div>
        )}

        {invite.status === "invalid" && <InviteOnlyNotice reason={invite.reason} />}

        {invite.status === "valid" && (
          <div className="ci-card p-8">
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
        </div>
      </div>
    </div>
  );
}
