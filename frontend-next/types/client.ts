/** A client as a billing entity -- what several cases can share, and what
 * the per-client statement groups on. Distinct from ClientContact (a
 * person to write to on one case). */
export type ClientType = "individual" | "business";

export interface Client {
  id: number;
  name: string;
  client_type: ClientType;
  client_type_display: string;
  /** Printed on invoices for a business client; never used to compute tax. */
  gstin: string;
  email: string;
  phone: string;
  address: string;
  notes: string;
  case_count: number;
  created_at: string;
  updated_at: string;
}

export interface ClientInput {
  name: string;
  client_type?: ClientType;
  gstin?: string;
  email?: string;
  phone?: string;
  address?: string;
  notes?: string;
}

/** Compact client embedded in a Case. */
export interface ClientSummary {
  id: number;
  name: string;
  client_type: ClientType;
}

// ---------------------------------------------------------------------------
// Client messages: system-written drafts the advocate reviews and sends
// ---------------------------------------------------------------------------

export type ClientMessageKind = "case_update" | "payment_reminder";
/** "logged" = recorded in the server log because email isn't configured.
 * It is never a delivery -- never render it as "sent". */
export type ClientMessageStatus = "draft" | "sent" | "logged" | "discarded";

export interface MessageRecipient {
  contact_id: number;
  name: string;
  email: string;
}

export interface ClientMessage {
  id: number;
  case: number;
  case_title: string;
  case_number: string;
  kind: ClientMessageKind;
  kind_display: string;
  status: ClientMessageStatus;
  status_display: string;
  subject: string;
  body: string;
  recipients: MessageRecipient[];
  /** Contacts on the case this draft could go to (empty once sent). */
  eligible_recipients: MessageRecipient[];
  edited_by_user: boolean;
  reminder_number: number | null;
  fee: number | null;
  invoice_number: string | null;
  hearing: number | null;
  hearing_date: string | null;
  court_order: number | null;
  sent_at: string | null;
  discard_reason: string;
  created_at: string;
  updated_at: string;
}

export interface ClientMessageUpdateInput {
  subject?: string;
  body?: string;
  recipient_contact_ids?: number[];
}

/** POST /api/client-messages/<id>/send/ -- 200 with sent=false (not an
 * error) when the server has no email credentials. */
export interface SendClientMessageResult {
  sent: boolean;
  recipients: string[];
  detail: string;
  missing_env_vars: string[];
  required_env_vars: string[];
  message: ClientMessage;
}

export interface SentMessage {
  id: number;
  sent_at: string;
  sent_by: number | null;
  sent_by_username: string | null;
  kind: ClientMessageKind | "invoice";
  kind_display: string;
  delivery: "sent" | "logged";
  delivery_display: string;
  to_emails: string[];
  cc_emails: string[];
  subject: string;
  body_sha256: string;
  case: number | null;
  case_title: string | null;
  case_number: string | null;
  message: number | null;
  fee: number | null;
}

// ---------------------------------------------------------------------------
// Document templates
// ---------------------------------------------------------------------------

export interface DocTemplateSummary {
  key: string;
  title: string;
  description: string;
}

export interface DocTemplateField {
  name: string;
  label: string;
  required: boolean;
  multiline: boolean;
  value: string;
  /** Where the value came from ("profile.advocate_name", "input", ...), or
   * "" when nothing filled it. */
  source: string;
  /** Where the advocate can fill it in permanently. */
  where: string;
  missing: boolean;
  /** A typed value can be written back to the case/contact/profile
   * ("Save for next time"). */
  savable?: boolean;
  /** A fixed set of answers -- rendered as a select, not free text. */
  choices?: string[];
}

export interface DocTemplateForCase extends DocTemplateSummary {
  contact_id: number | null;
  fields: DocTemplateField[];
  ready: boolean;
}

export interface GenerateDocumentInput {
  template: string;
  contact_id?: number | null;
  inputs?: Record<string, string>;
  /** Typed fields to also save back to the record. */
  save?: string[];
}

// ---------------------------------------------------------------------------
// Billing portfolio
// ---------------------------------------------------------------------------

export interface AgingBucket {
  label: "0-30" | "31-60" | "61-90" | "90+";
  count: number;
  amount: string;
}

interface OutstandingAmounts {
  invoiced_amount: string;
  invoiced_count: number;
  pending_amount: string;
  pending_count: number;
  oldest_invoice_days: number | null;
}

export interface ClientOutstanding extends OutstandingAmounts {
  client_id: number;
  client_name: string;
  client_type: ClientType;
  case_count: number;
}

export interface UnassignedOutstanding extends OutstandingAmounts {
  case_id: number;
  case_title: string;
  case_number: string;
  client_name: string;
}

export interface UninvoicedHearing {
  hearing_id: number;
  hearing_date: string;
  case_id: number;
  case_title: string;
  case_number: string;
  pending_amount: string;
  has_fee: boolean;
}

export interface BillingPortfolio {
  as_of: string;
  aging: AgingBucket[];
  totals: {
    invoiced_amount: string;
    invoiced_count: number;
    pending_amount: string;
    pending_count: number;
  };
  clients: ClientOutstanding[];
  clients_total: number;
  unassigned: UnassignedOutstanding[];
  unassigned_total: number;
  uninvoiced_hearings: UninvoicedHearing[];
  uninvoiced_hearings_total: number;
}

// ---------------------------------------------------------------------------
// Refresh all tracked cases
// ---------------------------------------------------------------------------

export interface RefreshRunResults {
  refreshed: number;
  rate_limited: number;
  failed: number;
  skipped: number;
  new_hearing_dates: number;
  drafts_created: number;
  /** Cases where the fetch found a new hearing date. Absent on runs from
   * before this was counted. */
  updated?: number;
}

export interface RefreshRun {
  job_id: number;
  current_job_id: number;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  total: number;
  done: number;
  results: RefreshRunResults;
  failures: { case_id: number; case_number: string; error: string }[];
  aborted_reason: string;
  error: string;
  created_at: string;
  finished_at: string | null;
}

/** GET /api/cases/refresh-all/ when the advocate has never run one. */
export type LatestRefreshRun = RefreshRun | { job_id: null };
