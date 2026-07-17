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
  className: string;
}

export function reasonForCase(
  caseId: number,
  hearingSoonCaseIds: Set<number>,
  ecourtsUpdateCaseIds: Set<number>,
  failedDocCaseIds: Set<number>,
): UrgencyReason {
  if (hearingSoonCaseIds.has(caseId)) {
    return { label: "Hearing this week", className: "bg-[#fdecec] text-[#b32e26]" };
  }
  if (ecourtsUpdateCaseIds.has(caseId)) {
    return { label: "eCourts update", className: "bg-[#ebf3fb] text-[#2f6fb0]" };
  }
  if (failedDocCaseIds.has(caseId)) {
    return { label: "Processing failed", className: "bg-[#fdecec] text-[#b32e26]" };
  }
  return { label: "Needs attention", className: "bg-gray-100 text-[#4b5468]" };
}
