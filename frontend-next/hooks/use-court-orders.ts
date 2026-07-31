import { useMutation, useQuery } from "@tanstack/react-query";
import { courtOrdersApi } from "@/lib/api/court-orders";
import type { CourtOrder } from "@/types";

// A blob: URL keeps its data alive until revoked. Revoking immediately
// would race the new tab's navigation, so hold it briefly -- the tab has
// loaded the PDF well inside this, and the blob is freed either way.
const BLOB_REVOKE_DELAY_MS = 60_000;

export const courtOrderKeys = {
  all: ["court-orders"] as const,
  lists: () => [...courtOrderKeys.all, "list"] as const,
  list: (caseId: number, date?: string) =>
    [...courtOrderKeys.lists(), caseId, date ?? null] as const,
};

/** Every order for a case (or just one date's, when `date` is given).
 *
 * The case-detail page fetches without a date and buckets client-side, so
 * a case with 20 hearings still costs one request. */
export function useCaseOrders(caseId: number, date?: string) {
  return useQuery({
    queryKey: courtOrderKeys.list(caseId, date),
    queryFn: () => courtOrdersApi.listForCase(caseId, date),
    enabled: !!caseId,
    // Orders only change when court tracking refreshes, which is
    // rate-limited to roughly hourly -- no need to re-fetch eagerly.
    staleTime: 5 * 60 * 1000,
  });
}

/** Open an order's PDF in a new tab.
 *
 * Same popup-safe shape as useViewDocument (hooks/use-documents.ts): the
 * blank tab is opened synchronously in onMutate, still inside the click's
 * call stack, because calling window.open() after an await reads as an
 * unsolicited popup to some browsers. It then points at an object URL
 * rather than a storage URL -- /api/orders/<id>/file/ streams the bytes
 * behind an ownership check and has no linkable public URL. */
export function useViewOrder() {
  return useMutation<string, unknown, number, { win: Window | null }>({
    mutationFn: async (orderId: number) => {
      const blob = await courtOrdersApi.fetchFile(orderId);
      return URL.createObjectURL(blob);
    },
    onMutate: () => ({
      win: typeof window !== "undefined" ? window.open("", "_blank") : null,
    }),
    onSuccess: (url, _orderId, context) => {
      if (context?.win) {
        context.win.location.href = url;
      } else if (typeof window !== "undefined") {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      setTimeout(() => URL.revokeObjectURL(url), BLOB_REVOKE_DELAY_MS);
    },
    onError: (_err, _orderId, context) => {
      context?.win?.close();
    },
  });
}

/** Group orders by their order_date for per-hearing-card lookup.
 *
 * Keys are the API's own YYYY-MM-DD strings. Undated orders (the portal
 * sometimes lists none) can't belong to a hearing date and are dropped. */
export function groupOrdersByDate(orders: CourtOrder[]): Map<string, CourtOrder[]> {
  const byDate = new Map<string, CourtOrder[]>();
  for (const order of orders) {
    if (!order.order_date) continue;
    const bucket = byDate.get(order.order_date);
    if (bucket) {
      bucket.push(order);
    } else {
      byDate.set(order.order_date, [order]);
    }
  }
  return byDate;
}

/** The map key for a hearing.
 *
 * Backend TIME_ZONE is UTC and eCourts hearings are stored at midnight UTC
 * on the portal's date (court_tracking._upsert_hearings), so the UTC date
 * of hearing_date is exactly the CourtOrder.order_date to match. */
export function hearingDateKey(hearingDate: string): string {
  const parsed = new Date(hearingDate);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString().slice(0, 10);
}
