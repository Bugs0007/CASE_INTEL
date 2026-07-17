const LAST_DASHBOARD_VISIT_KEY = "case_intel_last_dashboard_visit";

/** Timestamp of the previous dashboard visit, used as the `since` param for
 * "what changed since I last looked" queries. Returns null on first visit. */
export function getLastDashboardVisit(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(LAST_DASHBOARD_VISIT_KEY);
}

export function setLastDashboardVisit(iso: string): void {
  window.localStorage.setItem(LAST_DASHBOARD_VISIT_KEY, iso);
}
