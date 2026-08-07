import type { NestedAppearanceFee, NestedTravelBooking } from "./billing";
import type { OrderSummary } from "./court-order";

export type HearingType =
  | "preliminary"
  | "motion"
  | "trial"
  | "appeal"
  | "sentencing"
  | "arraignment"
  | "status"
  | "other";
export type HearingStatus =
  | "scheduled"
  | "completed"
  | "cancelled"
  | "postponed";

export type HearingSource = "manual" | "ecourts";

/** Cause-list state for a hearing.
 *
 * "not_published" and "not_listed" are deliberately different: before
 * the court publishes, absence from the list means nothing at all and
 * must render as "Not yet listed"; after publication it means the matter
 * genuinely isn't being heard. */
export type CauseListStatus =
  | "not_checked"
  | "not_published"
  | "listed"
  | "not_listed";

export interface Hearing {
  id: number;
  case: number;
  case_title: string;
  hearing_date: string;
  hearing_type: HearingType;
  hearing_type_display: string;
  location: string | null;
  judge: string | null;
  status: HearingStatus;
  status_display: string;
  notes: string | null;
  outcome: string | null;
  source: HearingSource;
  business_date: string | null;
  purpose: string | null;
  /** Embedded by the API so the hearing card can render its fee badge
   * without a request per hearing. Null when no fee has been recorded. */
  appearance_fee: NestedAppearanceFee | null;
  travel_bookings: NestedTravelBooking[];
  /** Written only by the `fetch_cause_lists` job, never by a client. */
  cause_list_status: CauseListStatus;
  cause_list_status_display: string;
  /** Item/serial number in the published list, e.g. "3". */
  cause_list_item_number: string;
  /** Court hall, e.g. "1" from "COURT NO. 1". */
  cause_list_court_hall: string;
  cause_list_stage: string;
  cause_list_checked_at: string | null;
  /** Order Overview for the order filed on this hearing's date, or null
   * when no order was filed that day (or it isn't summarised yet). */
  order_summary: OrderSummary | null;
  created_at: string;
  updated_at: string;
}

export interface HearingCreateInput {
  case: number;
  hearing_date: string;
  hearing_type: HearingType;
  location?: string;
  judge?: string;
  status?: HearingStatus;
  notes?: string;
  outcome?: string;
}

export interface HearingUpdateInput extends Partial<HearingCreateInput> {}
