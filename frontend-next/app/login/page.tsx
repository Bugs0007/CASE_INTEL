"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { setToken, setUsername as storeUsername } from "@/lib/auth";
import { login } from "@/lib/api/auth";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const data = await login(username, password);
      setToken(data.token);
      storeUsername(data.username);
      router.push("/dashboard");
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
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                placeholder="••••••••"
                required
                className="ci-input"
              />
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
            Create one
          </Link>
        </div>
      </div>
    </div>
  );
}
