import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { STATUS_COLOR, StatusSwatch } from "@/components/dashboard/status";
import { MINI_BUTTON_LIGHT } from "@/components/dashboard/seg-text";
import { STATUS_ORDER, STATUS_SHORT, STATUS_LABEL, type DashboardModel } from "@/lib/dashboard/model";
import { formatINR } from "@/lib/utils";
import type { BillingPortfolio } from "@/types";

export interface BillingState {
  data: BillingPortfolio | undefined;
  isLoading: boolean;
  error: unknown;
}

/** Next 14 days: one row per day -- label, a bar scaled to the busiest day,
 * and the count. Gold marks a day with hearings in more than one court. */
function NextDaysCard({ model }: { model: DashboardModel }) {
  const max = Math.max(1, ...model.days.map((d) => d.count));
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2.5">
        <CardTitle>Next 14 days</CardTitle>
        <span className="ci-chip ci-chip--none">{model.comingUp.total}</span>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-1.5">
          {model.days.map((d, i) => (
            <li
              key={d.day}
              aria-label={`${d.label}: ${d.count} ${d.count === 1 ? "hearing" : "hearings"}${
                d.multiCourt ? ` in ${d.courts.length} courts` : ""
              }`}
              className={`grid grid-cols-[84px_1fr_24px] items-center gap-2 text-xs ${
                i === 0 ? "font-bold text-gray-900" : "text-gray-600"
              }`}
            >
              <span>{d.label}</span>
              <span aria-hidden="true" className="h-2.5 rounded-[2px] bg-[var(--ci-ink-08)]">
                <span
                  className="block h-full rounded-[2px]"
                  style={{
                    width: `${(d.count / max) * 100}%`,
                    background: d.multiCourt ? "var(--ci-warn)" : "color-mix(in srgb, var(--ci-warn) 40%, white)",
                  }}
                />
              </span>
              <b className="text-right font-semibold tabular-nums text-gray-900">{d.count || ""}</b>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-gray-500">Gold marks a day with hearings in more than one court.</p>
      </CardContent>
    </Card>
  );
}

/** Your practice: every active case in one bar, by status. */
function PracticeCard({ model, onOpenMap }: { model: DashboardModel; onOpenMap: () => void }) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2.5">
        <CardTitle>Your practice</CardTitle>
        <span className="ci-chip ci-chip--none">{model.activeCaseCount}</span>
        <button type="button" onClick={onOpenMap} className={`${MINI_BUTTON_LIGHT} ml-auto`}>
          Open map
        </button>
      </CardHeader>
      <CardContent>
        {model.activeCaseCount === 0 ? (
          <p className="text-sm text-gray-500">No active cases yet.</p>
        ) : (
          <>
            <div
              role="img"
              aria-label={STATUS_ORDER.map((s) => `${model.counts[s]} ${STATUS_LABEL[s].toLowerCase()}`).join(", ")}
              className="flex h-3 gap-0.5 overflow-hidden rounded-[3px] bg-[var(--ci-ink-08)]"
            >
              {STATUS_ORDER.map((s) => (
                <i
                  key={s}
                  className="block min-w-0 rounded-[1px]"
                  style={{ flex: model.counts[s], background: STATUS_COLOR[s] }}
                />
              ))}
            </div>
            <ul className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12.5px] text-gray-600">
              {STATUS_ORDER.map((s) => (
                <li key={s} className="flex items-center gap-2" title={STATUS_LABEL[s]}>
                  <StatusSwatch status={s} className="h-[9px] w-[9px]" />
                  <span className="whitespace-nowrap">{STATUS_SHORT[s]}</span>
                  <b className="ml-auto font-bold tabular-nums text-gray-900">{model.counts[s]}</b>
                </li>
              ))}
            </ul>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function BillingCard({ billing }: { billing: BillingState }) {
  const { data } = billing;
  // Invoices carry no due date; "over 30 days" is the aging the Billing page
  // already buckets (31-60, 61-90, 90+).
  const old = data?.aging.filter((b) => b.label !== "0-30").reduce((n, b) => n + b.count, 0) ?? 0;
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2.5">
        <CardTitle>Billing</CardTitle>
        <Link href="/billing" className={`${MINI_BUTTON_LIGHT} ml-auto`}>
          Open billing
        </Link>
      </CardHeader>
      <CardContent>
        {billing.isLoading ? (
          <div className="space-y-2.5">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
          </div>
        ) : billing.error || !data ? (
          <p className="text-sm text-status-alert">Could not load billing.</p>
        ) : (
          <dl className="text-[13px]">
            {[
              ["Unbilled this month", String(data.uninvoiced_hearings_total)],
              ["Outstanding", formatINR(data.totals.invoiced_amount)],
              ["Unpaid over 30 days", String(old)],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between gap-3 border-b border-dashed border-gray-200 py-1.5 last:border-0">
                <dt className="text-gray-600">{label}</dt>
                <dd className="font-semibold tabular-nums text-gray-900">{value}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

/** The right-hand column of the Briefing. */
export function GlanceColumn({
  model,
  billing,
  onOpenMap,
}: {
  model: DashboardModel;
  billing: BillingState;
  onOpenMap: () => void;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <NextDaysCard model={model} />
      <PracticeCard model={model} onOpenMap={onOpenMap} />
      <BillingCard billing={billing} />
    </div>
  );
}
