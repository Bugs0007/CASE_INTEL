"use client";

import { UnderlineTabs } from "@/components/mobile/underline-tabs";
import { BILLING_FILTERS, fromPaise, type BillingFilter, type BillingSummary } from "@/lib/billing-model";
import { cn, formatINR, pluralize } from "@/lib/utils";

/** How each filter is named, on the tiles and in the heading over the list. */
export const FILTER_LABELS: Record<BillingFilter, string> = {
  open: "Outstanding",
  to_invoice: "To invoice",
  awaiting: "Awaiting payment",
  paid: "Paid this month",
};

interface TileSpec {
  filter: BillingFilter;
  amount: number;
  caption: string;
  /** The caption is a warning (overdue invoices). */
  alert?: boolean;
}

function tilesFor(summary: BillingSummary): TileSpec[] {
  const { outstanding, toInvoice, awaiting, paidThisMonth } = summary;
  return [
    {
      filter: "open",
      amount: outstanding.paise,
      caption: `${pluralize(outstanding.count, "charge")} unpaid`,
    },
    {
      filter: "to_invoice",
      amount: toInvoice.paise,
      caption: `${pluralize(toInvoice.count, "charge")} recorded, no invoice`,
    },
    {
      filter: "awaiting",
      amount: awaiting.paise,
      caption:
        awaiting.overdueCount > 0
          ? `${awaiting.overdueCount} overdue · oldest ${awaiting.oldestDays} d`
          : `${pluralize(awaiting.count, "invoice")} out`,
      alert: awaiting.overdueCount > 0,
    },
    {
      filter: "paid",
      amount: paidThisMonth.paise,
      caption: `${pluralize(paidThisMonth.count, "payment")} received`,
    },
  ];
}

/** Desktop: the four totals as a row of tiles that are also the filter --
 * press one to list just those charges. */
export function SummaryTiles({
  summary,
  active,
  onChange,
}: {
  summary: BillingSummary;
  active: BillingFilter;
  onChange: (filter: BillingFilter) => void;
}) {
  return (
    <div role="group" aria-label="Show charges" className="grid grid-cols-4 gap-3 max-md:hidden">
      {tilesFor(summary).map((tile) => (
        <button
          key={tile.filter}
          type="button"
          aria-pressed={active === tile.filter}
          onClick={() => onChange(tile.filter)}
          className={cn(
            "rounded-lg border bg-surface px-4 py-3 text-left transition-colors hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
            active === tile.filter ? "border-[var(--ci-ink)] ring-1 ring-[var(--ci-ink)]" : "border-gray-200",
          )}
        >
          <div className="text-xs font-medium text-gray-500">{FILTER_LABELS[tile.filter]}</div>
          <div
            key={tile.amount}
            className="animate-settle font-mono text-[22px] font-semibold leading-tight text-gray-900 motion-reduce:animate-none"
          >
            {formatINR(fromPaise(tile.amount))}
          </div>
          <div className={cn("text-xs", tile.alert ? "font-medium text-status-alert" : "text-gray-500")}>{tile.caption}</div>
        </button>
      ))}
    </div>
  );
}

/** Phone: the headline (everything unpaid, and how much of it is overdue) in
 * one card. The filter itself is the tab row pinned under the top bar. */
export function SummaryHero({ summary }: { summary: BillingSummary }) {
  const { outstanding, toInvoice, awaiting, paidThisMonth } = summary;
  return (
    <div className="ci-card px-4 py-3.5 md:hidden" data-testid="billing-hero">
      <div className="text-xs font-medium text-gray-500">Outstanding</div>
      <div
        key={outstanding.paise}
        className="animate-settle font-mono text-[28px] font-semibold leading-tight text-gray-900 motion-reduce:animate-none"
      >
        {formatINR(fromPaise(outstanding.paise))}
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div>
          <dt className="text-gray-500">Awaiting payment</dt>
          <dd className="font-mono text-sm text-gray-900">{formatINR(fromPaise(awaiting.paise))}</dd>
        </div>
        <div>
          <dt className="text-gray-500">To invoice</dt>
          <dd className="font-mono text-sm text-gray-900">{formatINR(fromPaise(toInvoice.paise))}</dd>
        </div>
      </dl>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {awaiting.overdueCount > 0 && (
          <span className="ci-chip ci-chip--alert">
            {awaiting.overdueCount} overdue · oldest {awaiting.oldestDays} d
          </span>
        )}
        <span className="text-xs text-gray-500">
          {formatINR(fromPaise(paidThisMonth.paise))} paid this month
        </span>
      </div>
    </div>
  );
}

const TAB_LABELS: Record<BillingFilter, string> = {
  open: "Unpaid",
  to_invoice: "To invoice",
  awaiting: "Awaiting",
  paid: "Paid",
};

/** Phone: the filter as tabs for the sticky strip under the top bar. Counts
 * say what each holds. */
export function BillingFilterTabs({
  summary,
  active,
  onChange,
}: {
  summary: BillingSummary;
  active: BillingFilter;
  onChange: (filter: BillingFilter) => void;
}) {
  const counts: Record<BillingFilter, number | null> = {
    open: summary.outstanding.count,
    to_invoice: summary.toInvoice.count,
    awaiting: summary.awaiting.count,
    paid: null,
  };
  return (
    <UnderlineTabs
      label="Show charges"
      active={active}
      onChange={onChange}
      tabs={BILLING_FILTERS.map((filter) => ({
        key: filter,
        label: (
          <>
            {TAB_LABELS[filter]}
            {counts[filter] !== null && <span className="ci-chip ci-chip--none !px-1.5">{counts[filter]}</span>}
          </>
        ),
      }))}
    />
  );
}
