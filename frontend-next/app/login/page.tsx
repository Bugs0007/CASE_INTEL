"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { setToken, setUsername as storeUsername } from "@/lib/auth";
import { API_BASE_URL } from "@/lib/api/client";

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
      const response = await fetch(`${API_BASE_URL}/auth/login/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      if (!response.ok) {
        setError("Invalid username or password.");
        return;
      }

      const data = await response.json();
      setToken(data.token);
      storeUsername(data.username);
      router.push("/");
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-page">
      <div className="w-[400px] max-w-[calc(100vw-40px)]">
        <div className="text-center mb-7">
          <div className="text-[22px] font-bold text-primary-active">Case Intel</div>
          <div className="text-sm text-gray-500 mt-1.5">Sign in to your workspace</div>
        </div>

        <div className="bg-white border border-gray-100 rounded-xl shadow-[0_1px_2px_rgba(20,23,31,0.04)] p-8">
          <form onSubmit={handleSubmit} className="flex flex-col gap-[18px]">
            <div>
              <label
                htmlFor="username"
                className="block text-[13px] font-semibold text-gray-700 mb-1.5"
              >
                Username
              </label>
              <input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                placeholder="advocate@caseintel.com"
                required
                className="w-full h-11 rounded-lg border border-gray-200 px-3.5 text-sm text-gray-800 outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
            <div>
              <label
                htmlFor="password"
                className="block text-[13px] font-semibold text-gray-700 mb-1.5"
              >
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
                className="w-full h-11 rounded-lg border border-gray-200 px-3.5 text-sm text-gray-800 outline-none focus:ring-2 focus:ring-primary/30"
              />
            </div>
            {error && (
              <div className="text-[13px] text-[#b32e26] bg-[#fdecec] rounded-lg px-3 py-2.5">
                {error}
              </div>
            )}
            <button
              type="submit"
              disabled={loading}
              className="w-full h-11 rounded-lg border-none bg-primary text-white text-sm font-semibold hover:bg-primary-hover disabled:opacity-50 disabled:pointer-events-none transition-colors"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>
        </div>
        <div className="text-center mt-[18px] text-[13px] text-gray-400">
          Trouble signing in? Contact your firm administrator.
        </div>
      </div>
    </div>
  );
}
