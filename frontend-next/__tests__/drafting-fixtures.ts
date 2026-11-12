import type { DraftBody, DraftDetail, DraftOutput, DraftRevision } from "@/types/draft";

export const body: DraftBody = {
  schema_version: 1,
  title: "Status memo",
  subtype: "status_memo",
  sections: [
    {
      heading: "Where things stand",
      blocks: [
        { type: "paragraph", text: "The matter is listed next week.", evidence: ["hearing:18"] },
        { type: "bullets", items: ["File reply", "Serve notice"], is_suggestion: true },
        { type: "table", columns: ["Date", "Event"], rows: [["1 Jan", "Hearing"]] },
      ],
    },
  ],
};

export const evidence = [
  {
    id: "hearing:18",
    kind: "hearing" as const,
    label: "Hearing on 12 Nov",
    ref: { kind: "hearing" as const, id: 18, case_id: 7, label: "Hearing on 12 Nov", recorded_at: null },
    fingerprint: "f",
  },
];

export function revision(over: Partial<DraftRevision> = {}): DraftRevision {
  return {
    id: 100,
    version: 1,
    source: "generated",
    created_at: "2026-11-01T10:00:00Z",
    approved_at: null,
    body,
    schema_version: 1,
    evidence,
    missing_facts: [],
    warnings: [],
    approved_hash: "",
    ...over,
  };
}

export function detail(over: Partial<DraftDetail> = {}): DraftDetail {
  const current = over.current_revision === undefined ? revision() : over.current_revision;
  return {
    id: 5,
    case_id: 7,
    kind: "document",
    subtype: "status_memo",
    status: "ready",
    approved_revision_id: null,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-01T10:00:00Z",
    case_title: "A v B",
    error: "",
    generation: 1,
    brief: { instructions: "", audience: "", tone: "neutral", length: "standard", source_document_ids: [] },
    current_revision: current,
    revisions: current
      ? [{ id: current.id, version: current.version, source: current.source, created_at: current.created_at, approved_at: current.approved_at }]
      : [],
    outputs: [],
    ...over,
  };
}

export function output(over: Partial<DraftOutput> = {}): DraftOutput {
  return {
    id: 900,
    revision_id: 100,
    destination: "docx",
    status: "ready",
    filename: "memo.docx",
    case_note_id: null,
    error: "",
    created_at: "2026-11-01T10:00:00Z",
    ...over,
  };
}
