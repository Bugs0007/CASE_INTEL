import { useEffect, useRef } from "react";
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { caseTrackingApi } from "@/lib/api/case-tracking";
import { isOrderSyncActive } from "@/lib/order-sync";
import { caseKeys } from "@/hooks/use-cases";
import { courtOrderKeys } from "@/hooks/use-court-orders";
import { documentKeys } from "@/hooks/use-documents";
import { hearingKeys } from "@/hooks/use-hearings";
import type { Case, OrderSyncState, OrderSyncStatus } from "@/types";

/** Everything an order check can add to: the case's documents, its orders
 * (the page's "case-orders" list and the per-date ones), the hearing rows
 * that show them, and the document count on the Cases list. */
export function invalidateOrderData(queryClient: QueryClient) {
  queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
  queryClient.invalidateQueries({ queryKey: courtOrderKeys.lists() });
  queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
  queryClient.invalidateQueries({ queryKey: caseKeys.lists() });
}

/** Re-reads the case's documents and orders when its order check finishes
 * having saved something: it moved from queued/running to ok (or partial)
 * with at least one PDF downloaded. A page opened on an already-settled case
 * does nothing -- its data was just fetched. */
export function useRefreshWhenOrdersArrive(orderSync: OrderSyncStatus | null | undefined) {
  const queryClient = useQueryClient();
  const previous = useRef<OrderSyncState | undefined>(undefined);
  const state = orderSync?.state;
  const downloaded = orderSync?.downloaded ?? 0;

  useEffect(() => {
    const before = previous.current;
    previous.current = state;
    if (isOrderSyncActive(before) && (state === "ok" || state === "partial") && downloaded > 0) {
      invalidateOrderData(queryClient);
    }
  }, [state, downloaded, queryClient]);
}

/** The Retry button: queue another order check. The case detail switches to
 * "queued" at once, which starts the 5-second poll in useCase. */
export function useRetryOrderCheck(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => caseTrackingApi.retryOrderCheck(caseId),
    onSuccess: ({ order_sync }) => {
      queryClient.setQueryData<Case>(caseKeys.detail(caseId), (old) => (old ? { ...old, order_sync } : old));
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
    },
  });
}
