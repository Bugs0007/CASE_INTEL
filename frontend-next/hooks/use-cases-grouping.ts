"use client";

import { useCallback, useState } from "react";
import { getUsername } from "@/lib/auth";
import { parseGrouping, type CaseGrouping } from "@/lib/case-grouping";

/** How the Cases list is grouped, and which groups are folded away.
 *
 * The grouping lives in the address bar (?group=court|client) and is also
 * remembered per user as the default for the next visit; the address bar wins
 * when both are there. Switching only changes state, the saved choice and the
 * address bar (history.replaceState -- no navigation, nothing refetched).
 * Folded groups are remembered per grouping, so folding the courts does not
 * fold the clients.
 *
 * Both are read once, when the page mounts (the Cases list only renders groups
 * after its data has loaded on the client, so there is no server markup to
 * disagree with). */

type Grouped = Exclude<CaseGrouping, "none">;

export function groupingStorageKey(userId: string | null): string {
  return `ci:cases-group:${userId ?? "anonymous"}`;
}

export function collapsedStorageKey(userId: string | null, grouping: Grouped): string {
  return `ci:cases-group-collapsed:${userId ?? "anonymous"}:${grouping}`;
}

/** The address bar first, then the saved choice, then no grouping. */
export function resolveInitialGrouping(urlValue: string | null, storedValue: string | null): CaseGrouping {
  return parseGrouping(urlValue) ?? parseGrouping(storedValue) ?? "none";
}

function readStored(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStored(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Not remembered (private mode); the choice still works for this visit.
  }
}

export function useCasesGrouping() {
  const [grouping, setGroupingState] = useState<CaseGrouping>(() =>
    typeof window === "undefined"
      ? "none"
      : resolveInitialGrouping(
          new URLSearchParams(window.location.search).get("group"),
          readStored(groupingStorageKey(getUsername())),
        ),
  );

  const setGrouping = useCallback((next: CaseGrouping) => {
    setGroupingState(next);
    writeStored(groupingStorageKey(getUsername()), next);
    const url = new URL(window.location.href);
    if (next === "none") url.searchParams.delete("group");
    else url.searchParams.set("group", next);
    window.history.replaceState(null, "", url);
  }, []);

  return { grouping, setGrouping };
}

function readCollapsed(grouping: Grouped): Set<string> {
  try {
    const parsed: unknown = JSON.parse(readStored(collapsedStorageKey(getUsername(), grouping)) ?? "[]");
    return new Set(Array.isArray(parsed) ? parsed.filter((k): k is string => typeof k === "string") : []);
  } catch {
    return new Set();
  }
}

const NOTHING_FOLDED: ReadonlySet<string> = new Set();

export function useCollapsedGroups(grouping: CaseGrouping) {
  const [folded, setFolded] = useState<Record<Grouped, Set<string>>>(() =>
    typeof window === "undefined"
      ? { court: new Set(), client: new Set() }
      : { court: readCollapsed("court"), client: readCollapsed("client") },
  );

  const update = useCallback(
    (change: (current: Set<string>) => Set<string>) => {
      if (grouping === "none") return;
      setFolded((all) => {
        const next = change(all[grouping]);
        writeStored(collapsedStorageKey(getUsername(), grouping), JSON.stringify([...next]));
        return { ...all, [grouping]: next };
      });
    },
    [grouping],
  );

  /** Fold one group if it is open, open it if it is folded. */
  const toggle = useCallback(
    (key: string) =>
      update((current) => {
        const next = new Set(current);
        if (!next.delete(key)) next.add(key);
        return next;
      }),
    [update],
  );

  /** Fold every group in `keys`, or open them all. */
  const setAll = useCallback(
    (keys: string[], fold: boolean) => update((current) => (fold ? new Set([...current, ...keys]) : new Set())),
    [update],
  );

  return { collapsed: grouping === "none" ? NOTHING_FOLDED : folded[grouping], toggle, setAll };
}
