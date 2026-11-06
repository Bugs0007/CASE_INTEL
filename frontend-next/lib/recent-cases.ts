/** The "Recent cases" list in the sidebar.
 *
 * Client-side only: localStorage, one key per signed-in user, holding just
 * `{ id, title }` for up to four cases, most recent first. Nothing about the
 * case beyond its title is kept, and nothing is sent anywhere. */

export const RECENT_CASES_MAX = 4;
export const RECENT_CASES_EVENT = "ci:recent-cases-changed";

export interface RecentCase {
  id: number;
  title: string;
}

export function recentCasesKey(userId: string | null): string {
  return `ci:recent-cases:${userId ?? "anonymous"}`;
}

function notify() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(RECENT_CASES_EVENT));
}

function isRecentCase(value: unknown): value is RecentCase {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as RecentCase).id === "number" &&
    typeof (value as RecentCase).title === "string"
  );
}

export function readRecentCases(userId: string | null): RecentCase[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(recentCasesKey(userId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(isRecentCase)
      .map(({ id, title }) => ({ id, title }))
      .slice(0, RECENT_CASES_MAX);
  } catch {
    return [];
  }
}

function write(userId: string | null, entries: RecentCase[]) {
  try {
    window.localStorage.setItem(recentCasesKey(userId), JSON.stringify(entries));
  } catch {
    // Storage can be full or blocked (private mode): the list is a
    // convenience, so it just isn't remembered.
  }
  notify();
}

/** Puts a case at the top, once, and keeps the newest four. */
export function pushRecentCase(userId: string | null, entry: RecentCase): void {
  if (typeof window === "undefined") return;
  const title = entry.title.trim();
  if (!title) return;
  const rest = readRecentCases(userId).filter((c) => c.id !== entry.id);
  write(userId, [{ id: entry.id, title }, ...rest].slice(0, RECENT_CASES_MAX));
}

export function removeRecentCase(userId: string | null, id: number): void {
  if (typeof window === "undefined") return;
  const before = readRecentCases(userId);
  const after = before.filter((c) => c.id !== id);
  if (after.length !== before.length) write(userId, after);
}

/** Forgets the list entirely -- called when the user logs out. */
export function clearRecentCases(userId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(recentCasesKey(userId));
  } catch {
    // Nothing to clear.
  }
  notify();
}
