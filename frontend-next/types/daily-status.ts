/** One District Courts "Daily Status" (Business on Date) entry, from
 * GET /api/cases/<id>/daily-status/ (newest first).
 *
 * Dates are plain calendar dates ("2026-11-05"), never instants: read them
 * as year/month/day, never through `new Date(iso)`. */
export interface DailyStatusEntry {
  business_date: string;
  court_name: string;
  business_text: string;
  next_purpose: string;
  next_hearing_date: string | null;
  /** When Case Intel read it from the portal (an ISO instant). */
  fetched_at: string;
}
