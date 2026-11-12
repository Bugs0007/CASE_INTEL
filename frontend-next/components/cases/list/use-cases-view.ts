"use client";

import { useCallback, useState } from "react";
import { getUsername } from "@/lib/auth";

/** The Cases page shows cards (the default) or a dense list; the choice is remembered per user. */
export type CasesView = "list" | "cards";

export function viewStorageKey(userId: string | null): string {
  return `ci:cases-view:${userId ?? "anonymous"}`;
}

function readStored(): CasesView {
  try {
    return window.localStorage.getItem(viewStorageKey(getUsername())) === "list" ? "list" : "cards";
  } catch {
    return "cards";
  }
}

export function useCasesView() {
  const [view, setViewState] = useState<CasesView>(() => (typeof window === "undefined" ? "cards" : readStored()));
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
