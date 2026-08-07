"use client";

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { IndianRupee } from "lucide-react";
import type { CaseFeeSummary } from "@/types";

interface CaseFeeSummaryCardProps {
  summary: CaseFeeSummary;
}

/** Amounts come off the API as decimal strings so money never
 * round-trips through a float. Parse for display only. */
function formatAmount(value: string): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return value;
  return amount.toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  });
}

/** Pending / paid position on this case's appearance fees.
 *
 * Renders nothing at all when the case has no fees recorded -- invoicing
 * is opt-in, and an all-zero card on every case would be noise for
 * advocates who don't use it. */
export function CaseFeeSummaryCard({ summary }: CaseFeeSummaryCardProps) {
  const totalCount =
    summary.pending_count + summary.invoiced_count + summary.paid_count;
  if (totalCount === 0) return null;

  const buckets = [
    {
      label: "Pending",
      hint: "Recorded but not yet invoiced",
      amount: summary.pending_amount,
      count: summary.pending_count,
      className: "text-[#8a5a0b]",
    },
    {
      label: "Invoiced",
      hint: "Billed, awaiting payment",
      amount: summary.invoiced_amount,
      count: summary.invoiced_count,
      className: "text-[#33449b]",
    },
    {
      label: "Paid",
      hint: "Received",
      amount: summary.paid_amount,
      count: summary.paid_count,
      className: "text-[#1d6b3f]",
    },
  ];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <IndianRupee className="h-4 w-4" />
          Appearance Fees
        </CardTitle>
        <div className="text-right">
          <div className="text-xs text-gray-400">Outstanding</div>
          <div className="text-sm font-semibold text-gray-900">
            {formatAmount(summary.outstanding_amount)}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 @sm:grid-cols-3 gap-4">
          {buckets.map((bucket) => (
            <div key={bucket.label} className="space-y-1">
              <dt className="text-xs text-gray-400" title={bucket.hint}>
                {bucket.label} ({bucket.count})
              </dt>
              <dd className={`text-sm font-semibold ${bucket.className}`}>
                {formatAmount(bucket.amount)}
              </dd>
            </div>
          ))}
        </div>
        <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between text-sm">
          <span className="text-gray-500">Total billed on this case</span>
          <span className="font-medium text-gray-900">
            {formatAmount(summary.total_amount)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
