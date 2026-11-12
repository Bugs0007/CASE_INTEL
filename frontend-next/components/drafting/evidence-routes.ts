import type { DraftEvidence } from "@/types/draft";

/** Where each kind of record lives. A link is built from the kind and ids of
 * the record, never from a URL the API sent. */
const ROUTE_BY_KIND: Record<DraftEvidence["kind"], (ref: DraftEvidence["ref"], caseId: number) => string> = {
  case: (ref, caseId) => `/cases/${ref.case_id ?? ref.id ?? caseId}`,
  hearing: (ref, caseId) => `/cases/${ref.case_id ?? caseId}`,
  task: (ref, caseId) => `/cases/${ref.case_id ?? caseId}`,
  event: (ref, caseId) => `/cases/${ref.case_id ?? caseId}`,
  document: (ref, caseId) => `/cases/${ref.case_id ?? caseId}?doc=${ref.id}`,
};

export function evidenceHref(evidence: DraftEvidence, caseId: number): string {
  const build = ROUTE_BY_KIND[evidence.kind];
  return build ? build(evidence.ref, caseId) : `/cases/${caseId}`;
}

export const EVIDENCE_KIND_LABEL: Record<DraftEvidence["kind"], string> = {
  case: "Case record",
  hearing: "Hearing",
  task: "Task",
  event: "Calendar event",
  document: "Document",
};
