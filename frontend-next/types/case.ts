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

export interface Case {
  id: number;
  case_number: string;
  title: string;
  client_name: string;
  opposing_party: string | null;
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
}

export interface CaseCreateInput {
  case_number: string;
  title: string;
  client_name: string;
  opposing_party?: string;
  case_type?: CaseType;
  status?: CaseStatus;
  priority?: CasePriority;
  filing_date?: string;
  notes?: string;
}

export interface CaseUpdateInput extends Partial<CaseCreateInput> {}
