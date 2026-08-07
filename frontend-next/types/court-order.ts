import type { ProcessingStatus } from "./document";

export type CourtOrderSource = "ecourts";

export type OrderSummaryStatus =
  | "pending"
  | "unreadable"
  | "no_directions"
  | "summarized"
  | "failed";

/** Which path the order took at ingest. Only "llm" cost money. */
export type OrderSummaryRoute = "unreadable" | "short" | "routine" | "llm";

/** The Order Overview, generated once at ingest and cached on the row.
 *
 * Directions are stored as the ORDER writes them (petitioner/respondent).
 * The your-side/other-side split is applied by the API from the case's
 * user_party_role, so `your_side_directions` is null when that role is
 * "unknown" -- in that case render both sides neutrally rather than
 * guessing, since acting on the wrong side's obligations is the real
 * harm here. */
export interface OrderSummary {
  status: OrderSummaryStatus;
  status_display: string;
  route: OrderSummaryRoute | "";
  what_happened: string;
  petitioner_directions: string[];
  respondent_directions: string[];
  /** Null when party_role is "unknown". */
  your_side_directions: string[] | null;
  other_side_directions: string[] | null;
  your_side_label: string | null;
  other_side_label: string | null;
  party_role: "unknown" | "petitioner" | "respondent";
  next_date: string | null;
  next_date_purpose: string;
  is_routine_adjournment: boolean;
  generated_at: string | null;
  error: string;
}

/** An order/judgment PDF fetched from the court portal for a case.
 *
 * Deliberately carries no storage path -- the file is reachable only via
 * GET /api/orders/<id>/file/, which re-checks ownership and streams the
 * bytes (see courtOrdersApi.fetchFile). */
export interface CourtOrder {
  id: number;
  /** Portal sequence, free text (e.g. "1", "10", "IA-3"). */
  order_number: string;
  /** ISO date (YYYY-MM-DD), or null when the portal listed no date. */
  order_date: string | null;
  description: string;
  judge: string;
  source: CourtOrderSource;
  /** False when the underlying Document row is gone -- not openable. */
  has_file: boolean;
  filename: string | null;
  file_size: number | null;
  processing_status: ProcessingStatus | null;
  summary: OrderSummary;
  created_at: string;
}
