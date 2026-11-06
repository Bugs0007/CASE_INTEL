"use client";

import { useSyncExternalStore } from "react";

/** Tailwind's `md` breakpoint: below this width the phone layouts apply. */
export const MOBILE_QUERY = "(max-width: 767px)";

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const mql = window.matchMedia(MOBILE_QUERY);
  mql.addEventListener("change", onChange);
  return () => mql.removeEventListener("change", onChange);
}

function getSnapshot(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(MOBILE_QUERY).matches
    : false;
}

/** True below 768px wide (Tailwind's `md`). The server and the first client
 * render answer false, so a page that picks a layout with this renders its
 * desktop form first and swaps on mount; pages that load their data on the
 * client show a skeleton at that moment, so nothing visibly jumps. Without
 * matchMedia (tests) it is always false: the desktop layout. */
export function useIsMobile(): boolean {
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}
