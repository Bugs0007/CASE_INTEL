"use client";

import { OrderSyncStatusLine } from "@/components/cases/order-sync-status";
import { showToast } from "@/components/ui/toaster";
import { useRetryOrderCheck } from "@/hooks/use-order-sync";
import type { Case } from "@/types";

/** The order-check status line inside the Documents and Hearings & orders
 * cards: the same line as everywhere else, with a working Retry button. */
export function CaseOrderCheckLine({ caseItem }: { caseItem: Case }) {
  const retry = useRetryOrderCheck(caseItem.id);
  return (
    <OrderSyncStatusLine
      caseItem={caseItem}
      className="px-0"
      retrying={retry.isPending}
      onRetry={() =>
        retry.mutate(undefined, {
          onError: (error) =>
            showToast.error(
              "Could not queue the check",
              error instanceof Error ? error.message : "Try again in a moment.",
            ),
        })
      }
    />
  );
}
