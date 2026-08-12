"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { setToken, setUsername as storeUsername } from "@/lib/auth";
import { register } from "@/lib/api/auth";
import { APIError } from "@/lib/api/client";

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await register(username, password, email);
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
          <div className="text-sm text-gray-500 mt-1.5">Create your workspace</div>
        </div>

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
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="••••••••"
                required
                className="ci-input"
              />
            </div>
            {error && <div className="ci-error bg-status-alert-soft rounded px-3 py-2.5 mt-0">{error}</div>}
            <button type="submit" disabled={loading} className="ci-btn ci-btn--solid w-full justify-center">
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>
        </div>
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
