import { apiBlob, apiClient } from "./client";
import type { CourtOrder } from "@/types";

export const courtOrdersApi = {
  /** Orders fetched from the court portal for a case.
   *
   * `date` (YYYY-MM-DD) narrows to one hearing date; omitting it returns
   * every order for the case, which is what the case-detail page does --
   * one request, then bucketed by date across the hearing cards. */
  listForCase: (caseId: number, date?: string) =>
    apiClient<CourtOrder[]>(`/cases/${caseId}/orders/`, {
      params: date ? { date } : undefined,
    }),

  /** The order's PDF bytes. Fetched (not linked) so the auth token can be
   * sent -- this endpoint streams through Django and has no public URL. */
  fetchFile: (orderId: number) => apiBlob(`/orders/${orderId}/file/`),
};
