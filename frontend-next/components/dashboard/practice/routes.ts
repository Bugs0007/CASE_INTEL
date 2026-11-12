import type { PracticeCalendarEntry, PracticeReference, RefKind } from "@/types/practice";

/** The one place a practice record becomes a link. Links come from a record's
 * kind and ids, never from text the assistant wrote. */
export const CALENDAR_ROUTE = "/calendar";
export const CASES_ROUTE = "/cases";
export const BILLING_ROUTE = "/billing";

const CASE_PAGE = (caseId: number) => `${CASES_ROUTE}/${caseId}`;

/** kind -> route. A kind that lives on a case page needs a case id and falls
 * back to the fallback route without one. */
const ROUTE_BY_KIND: Record<RefKind, { fallback: string; build: (ref: PracticeReference) => string | null }> = {
  case: { fallback: CASES_ROUTE, build: (ref) => CASE_PAGE(ref.case_id ?? ref.id) },
  hearing: { fallback: CALENDAR_ROUTE, build: (ref) => (ref.case_id ? CASE_PAGE(ref.case_id) : null) },
  task: { fallback: CALENDAR_ROUTE, build: (ref) => (ref.case_id ? CASE_PAGE(ref.case_id) : null) },
  event: { fallback: CALENDAR_ROUTE, build: (ref) => (ref.case_id ? CASE_PAGE(ref.case_id) : null) },
  document: { fallback: CASES_ROUTE, build: (ref) => (ref.case_id ? CASE_PAGE(ref.case_id) : null) },
  fee: { fallback: BILLING_ROUTE, build: () => null },
};

export function referenceHref(ref: Pick<PracticeReference, "kind" | "id" | "case_id">): string {
  const route = ROUTE_BY_KIND[ref.kind];
  if (!route) return CASES_ROUTE;
  return route.build(ref as PracticeReference) ?? route.fallback;
}

export function entryHref(entry: Pick<PracticeCalendarEntry, "kind" | "id" | "case_id">): string {
  return referenceHref(entry);
}

export function caseHref(caseId: number): string {
  return CASE_PAGE(caseId);
}
