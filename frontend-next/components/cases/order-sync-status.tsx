import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn, formatRelativeTime, pluralize } from "@/lib/utils";
import type { Case, OrderSyncStatus } from "@/types";

export interface OrderSyncLine {
  text: string;
  /** "warning" is amber: the check failed or left orders unfetched. */
  tone: "muted" | "warning";
  busy?: boolean;
  /** The check failed outright: offer a Retry button. */
  canRetry?: boolean;
}

/** The reason arrives as one of three fixed labels, never raw error text. */
function reasonText(reason: string | null): string {
  if (!reason || reason === "other") return "unexpected error";
  return reason;
}

/** The one-line "order check" status for the case page, or null when there
 * is nothing to say (the case is not tracked, so no order check is ever
 * run for it). Says what the check found, not what the page holds: the
 * Documents count is saved files only, and zero there can mean "none
 * published" or "never checked". */
export function describeOrderSync(
  status: OrderSyncStatus,
  trackingEnabled: boolean,
): OrderSyncLine | null {
  if (!trackingEnabled && status.state === "never") return null;
  const checked = formatRelativeTime(status.last_checked_at) || "just now";

  switch (status.state) {
    case "never":
      return { text: "Orders not checked yet", tone: "muted" };
    case "queued":
    case "running":
      return { text: "Checking eCourts for orders…", tone: "muted", busy: true };
    case "ok":
      return status.found === 0
        ? { text: `Checked eCourts ${checked}. No orders published for this case yet.`, tone: "muted" }
        : { text: `Checked ${checked}. ${pluralize(status.found, "order")}.`, tone: "muted" };
    case "partial":
      return {
        text: `${pluralize(status.found, "order")} found, ${status.downloaded} downloaded · the rest retry on the next refresh`,
        tone: "warning",
      };
    case "failed":
      return {
        text: `Last check failed (${reasonText(status.reason)}). Will retry.`,
        tone: "warning",
        canRetry: true,
      };
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

interface OrderSyncStatusLineProps {
  caseItem: Case;
  /** Shown as a Retry button when the check failed. Without it the line is text only. */
  onRetry?: () => void;
  retrying?: boolean;
  className?: string;
}

/** Whether the case page shows an order-check line at all (a tracked case,
 * or one that has been checked): the Documents card keeps a row of room
 * for it. */
export function hasOrderCheckLine(caseItem: Pick<Case, "order_sync" | "tracking_enabled">): boolean {
  return !!caseItem.order_sync && describeOrderSync(caseItem.order_sync, caseItem.tracking_enabled) !== null;
}

/** Muted status line for the case's order check. */
export function OrderSyncStatusLine({ caseItem, onRetry, retrying, className }: OrderSyncStatusLineProps) {
  if (!caseItem.order_sync) return null;
  const line = describeOrderSync(caseItem.order_sync, caseItem.tracking_enabled);
  if (!line) return null;
  return (
    <p
      data-testid="order-sync-status"
      data-state={caseItem.order_sync.state}
      className={cn(
        "flex items-start gap-1.5 px-1 text-xs",
        line.tone === "warning" ? "text-status-pending" : "text-gray-500",
        className,
      )}
    >
      {line.busy && <Loader2 className="mt-0.5 h-3 w-3 flex-shrink-0 animate-spin" aria-hidden />}
      {line.tone === "warning" && <AlertTriangle className="mt-0.5 h-3 w-3 flex-shrink-0" aria-hidden />}
      <span className="min-w-0 flex-1">{line.text}</span>
      {line.canRetry && onRetry && (
        <Button
          variant="secondary"
          size="sm"
          className="-my-1 h-8 flex-shrink-0 px-2 text-xs md:h-6"
          onClick={onRetry}
          disabled={retrying}
          aria-label="Retry order check"
        >
          {retrying ? "Retrying…" : "Retry"}
        </Button>
      )}
    </p>
  );
}
