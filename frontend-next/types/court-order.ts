import type { ProcessingStatus } from "./document";

export type CourtOrderSource = "ecourts";

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
  created_at: string;
}
