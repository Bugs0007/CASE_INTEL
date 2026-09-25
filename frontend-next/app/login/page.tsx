"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff } from "lucide-react";
import { setToken, setUsername as storeUsername } from "@/lib/auth";
import { login } from "@/lib/api/auth";

/** Where to go after signing in: the page a lapsed session was on (set by
 * lib/api/client.ts as ?next=). Same-site paths only -- never an open
 * redirect to another origin. */
function returnPath(): string | null {
  if (typeof window === "undefined") return null;
  const next = new URLSearchParams(window.location.search).get("next");
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/login")) return null;
  return next;
}

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  // Set by lib/api/client.ts when a request found the session gone (the
  // shared token was logged out elsewhere). Read after mount -- the page
  // is prerendered, so the query string isn't known at build time.
  const [sessionEnded, setSessionEnded] = useState(false);
  useEffect(() => {
    setSessionEnded(new URLSearchParams(window.location.search).get("expired") === "1");
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await login(username, password);
      setToken(data.token);
      storeUsername(data.username);
      router.push(returnPath() ?? "/dashboard");
    } catch {
      setError("Invalid username or password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="w-[400px] max-w-[calc(100vw-40px)]">
        <div className="text-center mb-7">
          <div className="font-serif text-[26px] text-gray-900">Case Intel</div>
          <div className="text-sm text-gray-500 mt-1.5">Sign in to your workspace</div>
        </div>

        {sessionEnded && (
          <div role="status" className="mb-4 rounded-lg border border-status-pending bg-status-pending-soft px-4 py-3 text-sm text-gray-800">
            Your session ended -- you were signed out, or this device wasn&apos;t used for a week. Sign in again to
            pick up where you left off.
          </div>
        )}

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
              <label htmlFor="password" className="ci-label">
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
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
            {error && <div className="ci-error bg-status-alert-soft rounded px-3 py-2.5 mt-0">{error}</div>}
            <button type="submit" disabled={loading} className="ci-btn ci-btn--solid w-full justify-center">
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>
        </div>
        <div className="text-center mt-[18px] text-[13px] text-gray-400">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-accent font-semibold hover:underline">
            Request access
          </Link>
        </div>
      </div>
    </div>
  );
}
