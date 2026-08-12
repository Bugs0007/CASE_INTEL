import type { Case } from "@/types";

/** Shared "needs attention this week" treatment — used identically by the
 * Dashboard's Cases-by-urgency section and the Cases list screen, so the
 * two never drift into different definitions of the same concept. */

const PRIORITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

export function sortByUrgencyPriority(cases: Case[]): Case[] {
  return cases
    .slice()
    .sort((a, b) => (PRIORITY_ORDER[a.priority] ?? 99) - (PRIORITY_ORDER[b.priority] ?? 99));
}

export interface UrgencyReason {
  label: string;
  /** One of the three ci-chip meanings (see components/ui/badge.tsx) --
   * "alert" is reserved for genuine failures, everything else that's
   * merely time-pressured or informational reads as pending/neutral. */
  chip: "ok" | "pending" | "alert" | "none";
}

export function reasonForCase(
  caseId: number,
  hearingSoonCaseIds: Set<number>,
  ecourtsUpdateCaseIds: Set<number>,
  failedDocCaseIds: Set<number>,
): UrgencyReason {
  if (hearingSoonCaseIds.has(caseId)) {
    return { label: "Hearing this week", chip: "pending" };
  }
  if (ecourtsUpdateCaseIds.has(caseId)) {
    return { label: "eCourts update", chip: "none" };
  }
  if (failedDocCaseIds.has(caseId)) {
    return { label: "Processing failed", chip: "alert" };
  }
  return { label: "Needs attention", chip: "pending" };
}
