/**
 * The structured body of an assistant draft.
 * Mirror of core/services/drafting/schema.py. Change both together.
 */

export const DRAFT_SCHEMA_VERSION = 1;

export type DraftSubtype = "status_memo" | "personal_note" | "client_letter" | "list_of_dates";

interface DraftBlockBase {
  /** Evidence IDs the server collected, e.g. "hearing:18", "doc:42:c310". */
  evidence?: string[];
  /** true = an advocacy suggestion, not a statement of fact */
  is_suggestion?: boolean;
}

export interface DraftParagraphBlock extends DraftBlockBase {
  type: "paragraph";
  text: string;
}

export interface DraftBulletsBlock extends DraftBlockBase {
  type: "bullets";
  items: string[];
}

export interface DraftTableBlock extends DraftBlockBase {
  type: "table";
  columns: string[];
  rows: string[][];
}

export type DraftBlock = DraftParagraphBlock | DraftBulletsBlock | DraftTableBlock;

export interface DraftSection {
  heading: string;
  blocks: DraftBlock[];
}

export interface DraftBody {
  schema_version: number;
  title: string;
  subtype: DraftSubtype;
  sections: DraftSection[];
  /** Facts the advocate must confirm before approval */
  verification_items?: string[];
  /** Non-blocking notes */
  warnings?: string[];
}

/* ------------------------------------------------------------------ *
 * Case assistant API (all under /api/case-assistant/ unless noted).
 * Every route answers 404 while CASE_DRAFTING_ENABLED is off.
 * ------------------------------------------------------------------ */

export type DraftKind = "document" | "note";
export type DraftStatus = "queued" | "generating" | "ready" | "failed";
export type DraftTone = "neutral" | "formal" | "plain";
export type DraftLength = "short" | "standard" | "detailed";
export type DraftRevisionSource = "generated" | "edited";
export type DraftDestination = "docx" | "case_note";
export type DraftOutputStatus = "pending" | "ready" | "failed";

export interface DraftBrief {
  instructions: string; // <= 2000 chars, may be ""
  audience: string; // <= 200 chars, may be ""
  tone: DraftTone;
  length: DraftLength;
  /** Documents of the same case. Empty = verified case records only. */
  source_document_ids: number[]; // <= 20
}

/** POST drafts/ -> 202 DraftDetail (200 on replay of the same request). */
export interface DraftCreateRequest extends Partial<DraftBrief> {
  case_id: number;
  subtype: DraftSubtype;
  origin_message_id?: number;
  client_request_id: string; // <= 64 chars
}

/** One thing the server collected. `id` is what a block's `evidence` cites. */
export interface DraftEvidence {
  id: string; // "case:104", "hearing:18", "task:7", "event:3", "doc:42:c310"
  kind: "case" | "hearing" | "task" | "event" | "document";
  label: string;
  ref: {
    kind: "case" | "hearing" | "task" | "event" | "document";
    id: number;
    case_id: number | null;
    label: string;
    recorded_at: string | null;
  };
  fingerprint: string;
}

export interface DraftRevisionSummary {
  id: number;
  version: number;
  source: DraftRevisionSource;
  created_at: string;
  approved_at: string | null;
}

/** GET drafts/{id}/revisions/{version}/ */
export interface DraftRevision extends DraftRevisionSummary {
  body: DraftBody;
  schema_version: number;
  evidence: DraftEvidence[];
  missing_facts: string[];
  warnings: string[];
  approved_hash: string;
}

export interface DraftOutput {
  id: number;
  revision_id: number;
  destination: DraftDestination;
  status: DraftOutputStatus;
  filename: string;
  case_note_id: number | null;
  error: string;
  created_at: string;
}

/** GET drafts/?case_id= returns DraftSummary[] (newest first, max 50). */
export interface DraftSummary {
  id: number;
  case_id: number;
  kind: DraftKind;
  subtype: DraftSubtype;
  status: DraftStatus;
  title: string; // current revision's title, "" before the first preview
  current_version: number | null;
  approved_revision_id: number | null;
  created_at: string;
  updated_at: string;
}

/** GET drafts/{id}/ and the body of every draft mutation. */
export interface DraftDetail extends Omit<DraftSummary, "title" | "current_version"> {
  case_title: string;
  error: string; // fixed safe message when status = failed
  generation: number;
  brief: DraftBrief;
  current_revision: DraftRevision | null;
  revisions: DraftRevisionSummary[]; // oldest first
  outputs: DraftOutput[]; // outputs of every revision of this draft
}

/** POST drafts/{id}/revisions/ -> 201 DraftDetail */
export interface DraftRevisionCreateRequest {
  expected_revision: number; // id of the revision the edit started from
  body: DraftBody;
}

/** POST drafts/{id}/approve/ -> 200 DraftDetail */
export interface DraftApproveRequest {
  revision_id: number;
  /** Required true when the revision has verification_items or missing_facts. */
  acknowledge_open_items?: boolean;
}

/** POST drafts/{id}/outputs/ -> 201 DraftOutput (200 when it already exists) */
export interface DraftOutputRequest {
  revision_id: number;
  destination: DraftDestination;
}

/**
 * Error bodies: { detail: string, code: DraftErrorCode, ...extra }.
 *  400 invalid_body        errors: string[]
 *  400 invalid_request     errors: { field: string[] } (malformed request fields)
 *  409 not_ready           edit or approval on a draft with no ready preview
 *  409 stale_revision      current_revision_id: number
 *  409 request_mismatch    same client_request_id, different payload
 *  409 not_retryable       retry on a draft that is not failed
 *  409 needs_acknowledgement  items: string[]
 *  409 evidence_changed    items: string[] (labels of evidence no longer present)
 *  409 not_approved        output requested for an unapproved revision
 *  429 draft_limit         too many drafts still generating
 */
export type DraftErrorCode =
  | "invalid_body"
  | "invalid_request"
  | "not_ready"
  | "stale_revision"
  | "request_mismatch"
  | "not_retryable"
  | "needs_acknowledgement"
  | "evidence_changed"
  | "not_approved"
  | "draft_limit";

/** GET /api/cases/{id}/notes/ -> CaseNote[]; DELETE /api/case-notes/{id}/ -> 204 */
export interface CaseNote {
  id: number;
  case_id: number;
  title: string;
  body: string; // plain text
  origin_draft_id: number | null;
  created_at: string;
  updated_at: string;
}
