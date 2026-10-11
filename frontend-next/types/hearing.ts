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
 * Absence from a list only means something when the WHOLE published list
 * was read, so the states that look alike must never be collapsed:
 *   not_published  the court has not put the list (or all of it) up yet
 *   not_listed     the full list is out and the matter is not in it
 *   fetch_failed   we could not get or read the list: "Couldn't check"
 *   unsupported    no source covers this court: "Not covered"
 */
export type CauseListStatus =
  | "not_checked"
  | "not_published"
  | "listed"
  | "not_listed"
  | "fetch_failed"
  | "unsupported";

/** One place a hearing appears in a published list (a matter can be in a
 * main and a supplementary list). */
export interface CauseListMatchInfo {
  item_number: string;
  court_hall: string;
  bench: string;
  list_type: string;
  stage: string;
  is_primary: boolean;
}

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
  /** Embedded by the API so the hearing card can render its charge badges
   * and rows without a request per hearing. Oldest first; empty when
   * nothing has been recorded. */
  appearance_fees: NestedAppearanceFee[];
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
  /** Bench / judges the matter is listed before. */
  cause_list_bench?: string;
  /** Which list, e.g. "DAILY LIST". */
  cause_list_list_type?: string;
  /** Why the state is what it is when not obvious, e.g. "3 of 58 lists not
   * uploaded yet", or the reason a court is not covered. */
  cause_list_note?: string;
  /** A link to the source list that works without a portal session; only
   * the Supreme Court has one. Blank otherwise. */
  cause_list_source_url?: string;
  cause_list_matches?: CauseListMatchInfo[];
  /** The court's own public cause-list page ("verify on the court's site"). */
  cause_list_verify_url?: string;
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
