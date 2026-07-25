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

export interface ClientContact {
  id: number;
  case: number;
  name: string;
  email: string | null;
  phone: string | null;
  role: ContactRole;
  is_billing_contact: boolean;
  created_at: string;
}

export interface ClientContactInput {
  case: number;
  name: string;
  email?: string;
  phone?: string;
  role: ContactRole;
  is_billing_contact: boolean;
}

export interface Case {
  id: number;
  case_number: string;
  title: string;
  client_name: string;
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
}

/** PATCH /api/cases/<id>/ -- a Case is never created directly (see
 * CaseListView); it always originates from the advocate-search/import
 * flow. This is the case-details form's write shape. */
export interface CaseUpdateInput {
  title?: string;
  opposing_party?: string;
  user_party_role?: UserPartyRole;
  case_type?: CaseType;
  status?: CaseStatus;
  priority?: CasePriority;
  filing_date?: string;
  notes?: string;
}
