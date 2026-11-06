"use client";

import { useRouter } from "next/navigation";
import { clearToken, clearUsername, getUsername } from "@/lib/auth";
import { logout } from "@/lib/api/auth";
import { clearRecentCases } from "@/lib/recent-cases";

/** Ends the session: invalidates the token on the server (best effort),
 * forgets the local sign-in and the recent-cases list, and goes to /login. */
export function useLogout() {
  const router = useRouter();

  return async function handleLogout() {
    const username = getUsername();
    // Best-effort: invalidate the token server-side too, so it can't be
    // reused if it ever leaked (e.g. from browser history/logs). Clear
    // local state and redirect regardless of whether the request succeeds.
    try {
      await logout();
    } catch {
      // Network error or already-invalid token -- proceed to clear local
      // state anyway, since the whole point is to end this session.
    }
    clearRecentCases(username);
    clearToken();
    clearUsername();
    router.push("/login");
  };
}
