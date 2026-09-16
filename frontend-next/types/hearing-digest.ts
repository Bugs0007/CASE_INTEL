// Mirrors core/serializers/hearing_digest.py (serialize_hearing_digest).

import type { OrderSummary } from "./court-order";
import type { CauseListStatus } from "./hearing";
import type { Task } from "./task";

/** ready: matches the current facts. stale/failed: older text may still be
 * shown, marked out of date. unavailable: nothing on record to brief on. */
export type BriefingStatus =
  | "ready"
  | "generating"
  | "stale"
  | "missing"
  | "failed"
  | "unavailable";

export interface CaseBriefingState {
  status: BriefingStatus;
  text: string;
  generated_at: string | null;
  error: string;
}

export interface HearingDigest {
  hearing: {
    id: number;
    hearing_date: string;
    hearing_type_display: string;
    status: string;
    status_display: string;
    judge: string;
    location: string;
    purpose: string;
    cause_list: {
      status: CauseListStatus;
      status_display: string;
      item_number: string;
      court_hall: string;
      stage: string;
      checked_at: string | null;
    };
  };
  case: {
    id: number;
    case_number: string;
    title: string;
    cnr_number: string | null;
    court_type: string | null;
    user_party_role: "unknown" | "petitioner" | "respondent";
    last_fetched_at: string | null;
    case_status: string;
    case_stage: string;
    court_and_judge: string;
  };
  /** What the hearing is for, most specific first. */
  purposes: string[];
  last_order: {
    id: number;
    order_number: string;
    order_date: string | null;
    has_file: boolean;
    summary: OrderSummary;
  } | null;
  open_tasks: Task[];
  documents: {
    id: number;
    filename: string;
    document_type: string | null;
    document_type_display: string;
    processing_status: string;
    document_date: string | null;
    created_at: string;
  }[];
  briefing: CaseBriefingState;
}
