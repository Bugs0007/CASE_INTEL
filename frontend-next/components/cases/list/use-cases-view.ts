"use client";

import { useCallback, useState } from "react";
import { getUsername } from "@/lib/auth";

/** The Cases page shows a dense list or cards; the choice is remembered per user. */
export type CasesView = "list" | "cards";

export function viewStorageKey(userId: string | null): string {
  return `ci:cases-view:${userId ?? "anonymous"}`;
}

function readStored(): CasesView {
  try {
    return window.localStorage.getItem(viewStorageKey(getUsername())) === "cards" ? "cards" : "list";
  } catch {
    return "list";
  }
}

export function useCasesView() {
  const [view, setViewState] = useState<CasesView>(() => (typeof window === "undefined" ? "list" : readStored()));
  const setView = useCallback((next: CasesView) => {
    setViewState(next);
    try {
      window.localStorage.setItem(viewStorageKey(getUsername()), next);
    } catch {
      // Private window or blocked storage: the choice just is not remembered.
    }
  }, []);
  return { view, setView };
}
