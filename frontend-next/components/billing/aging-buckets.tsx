import { cn } from "@/lib/utils";
import type { AgingBucket } from "@/types";

export function formatRupees(amount: string | number): string {
  const n = typeof amount === "string" ? Number(amount) : amount;
  return `Rs. ${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

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
          className={cn("rounded-lg border-l-4 border bg-surface px-3 py-2.5", TONE[b.label])}
        >
          <div className="text-xs text-gray-500">{b.label} days</div>
          <div className="font-mono text-base font-semibold text-gray-900">{formatRupees(b.amount)}</div>
          <div className="text-xs text-gray-500">
            {b.count} invoice{b.count === 1 ? "" : "s"}
          </div>
        </div>
      ))}
    </div>
  );
}
