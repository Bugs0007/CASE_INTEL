import { AlertTriangle, Loader2 } from "lucide-react";
import { formatRelativeTime, pluralize } from "@/lib/utils";
import type { Case, OrderSyncStatus } from "@/types";

export interface OrderSyncLine {
  text: string;
  /** "warning" is amber: the check failed or left orders unfetched. */
  tone: "muted" | "warning";
  busy?: boolean;
}

/** The reason arrives as one of three fixed labels, never raw error text. */
function reasonText(reason: string | null): string {
  if (!reason || reason === "other") return "unexpected error";
  return reason;
}

/** The one-line "order check" status for the case page, or null when there
 * is nothing to say (the case is not tracked, so no order check is ever
 * run for it). */
export function describeOrderSync(
  status: OrderSyncStatus,
  trackingEnabled: boolean,
): OrderSyncLine | null {
  if (!trackingEnabled && status.state === "never") return null;
  const checked = formatRelativeTime(status.last_checked_at);

  switch (status.state) {
    case "never":
      return { text: "Orders not checked yet", tone: "muted" };
    case "queued":
      return { text: "Order check queued…", tone: "muted", busy: true };
    case "running":
      return { text: "Checking the court portal for orders…", tone: "muted", busy: true };
    case "ok":
      return status.found === 0
        ? {
            text: `No orders found on the court portal${checked ? ` · checked ${checked}` : ""}`,
            tone: "muted",
          }
        : {
            text: `Orders last checked ${checked || "recently"} · ${pluralize(status.found, "order")} found`,
            tone: "muted",
          };
    case "partial":
      return {
        text: `${pluralize(status.found, "order")} found, ${status.downloaded} downloaded · the rest retry on the next refresh`,
        tone: "warning",
      };
    case "failed": {
      const lastGood = formatRelativeTime(status.last_success_at);
      return {
        text:
          `Last order check failed (${reasonText(status.reason)}), retries on next refresh` +
          (lastGood ? ` · last successful check ${lastGood}` : ""),
        tone: "warning",
      };
    }
  }
}

/** Short amber marker for the Cases card, or null. A tracked case whose
 * order check failed, only partly worked, or never ran must not read as a
 * bare "0 docs": that zero is "unknown", not "none". */
export function orderCheckMarker(caseItem: Pick<Case, "order_sync" | "tracking_enabled" | "document_count">): string | null {
  const { order_sync: sync, tracking_enabled: tracked, document_count: docs } = caseItem;
  if (!tracked || !sync) return null;
  if (sync.state === "failed") return "order check failed";
  if (sync.state === "partial") return "orders partly fetched";
  if (sync.state === "never" && docs === 0) return "orders not checked";
  return null;
}

/** Muted status line near the case's documents. */
export function OrderSyncStatusLine({ caseItem }: { caseItem: Case }) {
  if (!caseItem.order_sync) return null;
  const line = describeOrderSync(caseItem.order_sync, caseItem.tracking_enabled);
  if (!line) return null;
  return (
    <p
      data-testid="order-sync-status"
      data-state={caseItem.order_sync.state}
      className={`flex items-center gap-1.5 px-1 text-xs ${line.tone === "warning" ? "text-status-pending" : "text-gray-500"}`}
    >
      {line.busy && <Loader2 className="h-3 w-3 animate-spin" aria-hidden />}
      {line.tone === "warning" && <AlertTriangle className="h-3 w-3 flex-shrink-0" aria-hidden />}
      <span>{line.text}</span>
    </p>
  );
}
