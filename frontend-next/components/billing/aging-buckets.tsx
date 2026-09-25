import { cn, formatINR } from "@/lib/utils";
import type { AgingBucket } from "@/types";

/** Amber for overdue, red for long overdue -- but only when the bucket
 * actually holds invoices. An empty bucket is not a warning. */
const TONE: Record<AgingBucket["label"], string> = {
  "0-30": "border-gray-200",
  "31-60": "border-status-pending",
  "61-90": "border-status-pending",
  "90+": "border-status-alert",
};

/** Invoiced-and-unpaid money by how long it has been out. Each fee is its
 * own invoice, so the age is per fee from its invoice date. */
export function AgingBuckets({ buckets }: { buckets: AgingBucket[] }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="aging-buckets">
      {buckets.map((b) => (
        <div
          key={b.label}
          data-empty={b.count === 0 ? "true" : undefined}
          className={cn(
            "rounded-lg border-l-4 border bg-surface px-3 py-2.5",
            b.count > 0 ? TONE[b.label] : "border-gray-200",
          )}
        >
          <div className="text-xs text-gray-500">{b.label} days</div>
          <div
            className={cn(
              "font-mono text-base font-semibold",
              b.count > 0 ? "text-gray-900" : "text-gray-400",
            )}
          >
            {formatINR(b.amount)}
          </div>
          <div className="text-xs text-gray-500">
            {b.count} invoice{b.count === 1 ? "" : "s"}
          </div>
        </div>
      ))}
    </div>
  );
}
