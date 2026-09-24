import type { CaseFeeSummary } from "./billing";
import type { ClientSummary } from "./client";

export type CaseStatus = "open" | "closed" | "pending" | "archived";
export type CasePriority = "low" | "medium" | "high" | "critical";
export type CaseType =
  | "civil"
  | "criminal"
  | "family"
  | "corporate"
  | "ip"
  | "labor"
  | "tax"
  | "other";

export type CourtType = "district" | "high_court";
export type FetchStatus = "never_fetched" | "success" | "failed";
export type UserPartyRole = "unknown" | "petitioner" | "respondent";
export type ContactRole = "primary" | "assistant";
/** How the executant is described on a vakalatnama ("S/o Venkat Rao"). */
export type RelationType = "" | "s/o" | "d/o" | "w/o" | "c/o";

export interface ClientContact {
  id: number;
  case: number;
  name: string;
  email: string | null;
  phone: string | null;
  role: ContactRole;
  is_billing_contact: boolean;
  /** Opt-outs, re-checked at send time. */
  receive_case_updates: boolean;
  receive_payment_reminders: boolean;
  /** Executant details for generated documents. */
  relation_type: RelationType;
  relation_name: string;
  age: number | null;
  address: string;
  created_at: string;
}

export interface ClientContactInput {
  case: number;
  name: string;
  email?: string;
  phone?: string;
  role: ContactRole;
  is_billing_contact: boolean;
  receive_case_updates?: boolean;
  receive_payment_reminders?: boolean;
  relation_type?: RelationType;
  relation_name?: string;
  age?: number | null;
  address?: string;
}

export interface Case {
  id: number;
  case_number: string;
  title: string;
  client_name: string;
  /** The billing entity this case belongs to, if linked. */
  client: number | null;
  client_detail: ClientSummary | null;
  client_contacts: ClientContact[];
  opposing_party: string | null;
  user_party_role: UserPartyRole;
  case_type: CaseType | null;
  status: CaseStatus;
  priority: CasePriority;
  filing_date: string | null;
  notes: string | null;
  created_at: string;
  document_count: number;
  hearing_count: number;
  thread_count: number;
  conversation_count: number;
  cnr_number: string | null;
  court_type: CourtType | null;
  tracking_config: Record<string, string> | null;
  tracking_enabled: boolean;
  fetch_status: FetchStatus;
  last_fetched_at: string | null;
  needs_attention: boolean;
  next_hearing_date: string | null;
  fee_summary: CaseFeeSummary;
  // --- Case detail only (GET /api/cases/<id>/, CaseDetailSerializer) ---
  /** The parties as the court record gives them (set on every fetch). */
  petitioner_name?: string;
  respondent_name?: string;
  /** What the latest successful eCourts fetch said, null if never fetched. */
  tracking_snapshot?: TrackingSnapshot | null;
  tracking_freshness?: TrackingFreshness;
  /** The case looks disposed of -- the page offers to close it. */
  disposal?: CaseDisposal | null;
  /** Contacts who can receive case-update emails. 0 = no drafts are written. */
  update_recipient_count?: number;
  /** Petitioner/respondent from the court record, else the "X vs Y" title,
   * plus which one is ours/opposing given user_party_role. */
  parties?: CaseParties;
}

export interface CaseParties {
  petitioner: string;
  respondent: string;
  /** "record" (eCourts), "title" (split from "X vs Y"), or "" (neither). */
  source: "record" | "title" | "";
  ours: string;
  opposing: string;
}

export interface TrackingSnapshot {
  case_status: string | null;
  case_stage: string | null;
  court_and_judge: string | null;
  court_name: string | null;
  nature_of_disposal: string | null;
  next_hearing_date: string | null;
}

export interface TrackingFreshness {
  /** Last check older than stale_after_days, or a past hearing still
   * marked scheduled. */
  stale: boolean;
  reasons: ("last_checked" | "past_hearing_unconfirmed")[];
  stale_after_days: number;
  awaiting_update_count: number;
  /** Set while Refresh is rate-limited (one real fetch per hour). */
  refresh_available_at: string | null;
}

export interface CaseDisposal {
  source: "ecourts" | "order";
  detail: string;
  order_id: number | null;
  order_date: string | null;
}

/** PATCH /api/cases/<id>/ -- the case-details form's write shape. */
export interface CaseUpdateInput {
  title?: string;
  client?: number | null;
  opposing_party?: string;
  user_party_role?: UserPartyRole;
  case_type?: CaseType;
  status?: CaseStatus;
  priority?: CasePriority;
  filing_date?: string;
  notes?: string;
}

/** POST /api/cases/ -- manual case entry, the alternative to the
 * advocate-search/import flow. Deliberately excludes cnr_number/
 * court_type/tracking_config: those are only ever set afterwards, through
 * the court-tracking setup flow on the case detail page, the same way for
 * a manually-entered case as for an imported one. */
export interface CaseCreateInput {
  case_number: string;
  title: string;
  opposing_party?: string;
  user_party_role?: UserPartyRole;
  case_type?: CaseType;
  status?: CaseStatus;
  priority?: CasePriority;
  filing_date?: string;
  notes?: string;
  /** Confirms creation despite possible conflicts of interest (the API
   * answers 409 with code "conflict_check" until this is sent). */
  acknowledge_conflicts?: boolean;
}
