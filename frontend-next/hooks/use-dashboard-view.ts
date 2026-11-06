"use client";

import { useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import { getUsername } from "@/lib/auth";

export type DashboardView = "brief" | "map";

export function dashboardViewKey(userId: string | null): string {
  return `ci:dashboard-view:${userId ?? "anonymous"}`;
}

export function parseView(value: string | null | undefined): DashboardView | null {
  return value === "brief" || value === "map" ? value : null;
}

/** Which view opens: the URL (?view=brief|map) first, then the saved
 * choice, then the Briefing. */
export function resolveInitialView(urlValue: string | null, storedValue: string | null): DashboardView {
  return parseView(urlValue) ?? parseView(storedValue) ?? "brief";
}

function readStored(): string | null {
  try {
    return window.localStorage.getItem(dashboardViewKey(getUsername()));
  } catch {
    return null;
  }
}

/** The Briefing / Practice map choice.
 *
 * Switching only changes state, the saved choice and the address bar
 * (history.replaceState -- no navigation), so both views keep rendering
 * from the data the page already has: nothing is refetched and no loader
 * appears. Read once on mount; the page only mounts after AuthGuard has run
 * on the client, so localStorage is there. */
export function useDashboardView() {
  const params = useSearchParams();
  const [view, setViewState] = useState<DashboardView>(() =>
    resolveInitialView(params.get("view"), readStored()),
  );

  const setView = useCallback((next: DashboardView) => {
    setViewState(next);
    try {
      window.localStorage.setItem(dashboardViewKey(getUsername()), next);
    } catch {
      // Not remembered (private mode); the switch still works.
    }
    const url = new URL(window.location.href);
    url.searchParams.set("view", next);
    window.history.replaceState(null, "", url);
  }, []);

  return { view, setView };
}
