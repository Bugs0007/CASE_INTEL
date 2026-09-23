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
