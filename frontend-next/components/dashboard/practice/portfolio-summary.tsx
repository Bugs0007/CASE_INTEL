"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PortfolioSnapshot } from "@/types/practice";
import { formatAsOf, formatHearingDay, humanize } from "./format";
import { CASES_ROUTE, caseHref } from "./routes";

export interface PortfolioSummaryProps {
  snapshot: PortfolioSnapshot | null;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  /** 1-based page number to show next. */
  onPageChange: (page: number) => void;
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-0 rounded-lg border border-gray-100 px-3 py-2">
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="text-xl font-semibold text-gray-900">{value}</dd>
    </div>
  );
}

/** Exact portfolio totals and one page of the case list. */
export function PortfolioSummary({ snapshot, loading, error, onRetry, onPageChange }: PortfolioSummaryProps) {
  const pageCount = snapshot ? Math.max(1, Math.ceil(snapshot.total / snapshot.page_size)) : 1;
  const asOf = snapshot ? formatAsOf(snapshot.as_of) : "";

  return (
    <Card aria-labelledby="practice-portfolio-title">
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle id="practice-portfolio-title">Your cases</CardTitle>
        <Link
          href={CASES_ROUTE}
          className="inline-flex h-11 items-center text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-8"
        >
          Open all cases
        </Link>
      </CardHeader>
      <CardContent className="space-y-3 px-3 sm:px-5">
        {loading && (
          <div role="status" aria-busy="true" className="space-y-2">
            <p className="text-sm text-gray-500">Loading your cases.</p>
            <div className="h-16 animate-pulse rounded-lg bg-gray-100" />
          </div>
        )}

        {!loading && error && (
          <div role="alert" className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
            <p className="text-sm text-red-800">Your cases could not be loaded.</p>
            <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
              Try again
            </Button>
          </div>
        )}

        {!loading && !error && snapshot && snapshot.total_cases === 0 && (
          <p className="text-sm text-gray-500">You have no cases yet.</p>
        )}

        {!loading && !error && snapshot && snapshot.total_cases > 0 && (
          <>
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Total cases" value={snapshot.total_cases} />
              <Stat label="Active" value={snapshot.active_cases} />
              <Stat label="With a next hearing" value={snapshot.active_with_next_hearing} />
              <Stat label="No date scheduled" value={snapshot.active_without_next_date} />
            </dl>

            <ul aria-label="Cases by status" className="flex flex-wrap gap-1.5">
              {Object.entries(snapshot.status_counts).map(([status, count]) => (
                <li key={status} className="ci-chip ci-chip--none">
                  {humanize(status)} {count}
                </li>
              ))}
            </ul>

            <ul aria-label="Cases" className="space-y-1">
              {snapshot.cases.map((row) => (
                <li key={row.id}>
                  <Link
                    href={caseHref(row.id)}
                    className="flex min-h-[44px] flex-col gap-0.5 rounded-lg border border-gray-100 px-3 py-2 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="min-w-0 break-words text-sm font-medium text-gray-900">{row.title}</span>
                      <span className="ci-chip ci-chip--none">{humanize(row.status)}</span>
                    </span>
                    <span className="break-words text-xs text-gray-500">
                      {[row.court, row.next_hearing_at ? `Next hearing ${formatHearingDay(row.next_hearing_at)}` : "No next hearing"]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>

            <nav aria-label="Case list pages" className="flex items-center justify-between gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={snapshot.page <= 1}
                onClick={() => onPageChange(snapshot.page - 1)}
              >
                Previous page
              </Button>
              <span className="text-xs text-gray-600">
                Page {snapshot.page} of {pageCount}
              </span>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={snapshot.page >= pageCount}
                onClick={() => onPageChange(snapshot.page + 1)}
              >
                Next page
              </Button>
            </nav>
            {asOf && <p className="text-xs text-gray-500">Updated {asOf}</p>}
          </>
        )}
      </CardContent>
    </Card>
  );
}
