"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Search, X } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { showToast } from "@/components/ui/toaster";
import { AgingBuckets } from "@/components/billing/aging-buckets";
import { BillingFilterTabs, SummaryHero, SummaryTiles } from "@/components/billing/billing-summary";
import { FeeGroupCard } from "@/components/billing/fee-group";
import { MarkPaidSheet } from "@/components/billing/mark-paid-sheet";
import { UnbilledHearings } from "@/components/billing/unbilled-hearings";
import { BILLING_TABS, SectionTabs } from "@/components/layout/section-tabs";
import { MobileSubbar } from "@/components/layout/mobile-chrome";
import { useBillingFees } from "@/hooks/use-billing";
import { useCases, useUpdateCase } from "@/hooks/use-cases";
import { billingPortfolioKeys, useBillingPortfolio, useClients, useViewClientStatement } from "@/hooks/use-clients";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { apiErrorDetail } from "@/lib/api/client";
import {
  PAID_PAGE_SIZE,
  agingBuckets,
  buildFeeRows,
  filterRows,
  groupRows,
  newestPaid,
  summarize,
  type BillingFilter,
  type FeeRow,
} from "@/lib/billing-model";
import { istDayKey } from "@/lib/dashboard/dates";
import { pluralize, staggerDelay } from "@/lib/utils";

const HEADINGS: Record<BillingFilter, string> = {
  open: "Outstanding by client",
  to_invoice: "To invoice, by client",
  awaiting: "Awaiting payment, by client",
  paid: "Recently paid, by client",
};

const EMPTY: Record<BillingFilter, string> = {
  open: "Nothing is waiting on you: every charge you have recorded has been invoiced and paid.",
  to_invoice: "Nothing is waiting to be invoiced.",
  awaiting: "No invoice is waiting for payment.",
  paid: "Nothing has been marked paid yet.",
};

/** Billing across every case: what is owed and by whom, which invoices are
 * overdue, the one action each charge can take (generate its invoice, mark it
 * paid) and which of this month's hearings were never billed. */
export default function BillingPage() {
  const fees = useBillingFees();
  const casesQuery = useCases("all");
  const portfolio = useBillingPortfolio();
  const { data: clients = [] } = useClients();
  const viewStatement = useViewClientStatement();
  const updateCase = useUpdateCase();
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();

  const [filter, setFilter] = useState<BillingFilter>("open");
  const [query, setQuery] = useState("");
  const [showAllPaid, setShowAllPaid] = useState(false);
  const [sheet, setSheet] = useState<{ rows: FeeRow[]; open: boolean }>({ rows: [], open: false });

  const feeData = fees.data;
  const caseData = casesQuery.data;
  // The India day the page is read on; refreshed whenever the fees are.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const today = useMemo(() => istDayKey(), [feeData]);
  const rows = useMemo(
    () => (feeData && caseData ? buildFeeRows(feeData, caseData, today) : []),
    [feeData, caseData, today],
  );
  const summary = useMemo(() => summarize(rows, today), [rows, today]);
  const matched = useMemo(() => filterRows(rows, filter, query), [rows, filter, query]);
  const shown = useMemo(
    () => (filter === "paid" && !showAllPaid ? newestPaid(matched, PAID_PAGE_SIZE) : matched),
    [matched, filter, showAllPaid],
  );
  const groups = useMemo(() => groupRows(shown, filter), [shown, filter]);
  const aging = useMemo(() => agingBuckets(rows), [rows]);

  const loading = fees.isLoading || casesQuery.isLoading;
  const failed = !loading && (fees.isError || casesQuery.isError || !feeData || !caseData);

  function openStatement(clientId: number) {
    viewStatement.mutate(clientId, {
      onError: (e) => showToast.error("Could not open the statement", apiErrorDetail(e, "Please try again.")),
    });
  }

  async function assign(caseId: number, clientId: number) {
    try {
      await updateCase.mutateAsync({ id: caseId, data: { client: clientId } });
      queryClient.invalidateQueries({ queryKey: billingPortfolioKeys.all });
      showToast.success("Client assigned");
    } catch (e) {
      showToast.error("Could not assign the client", apiErrorDetail(e, "Please try again."));
    }
  }

  /** The pinned tabs change the list from wherever the page is scrolled to;
   * the new list is usually shorter, so bring its top back into view rather
   * than leave the page on whatever is now at that scroll position. */
  function changeFilterFromTabs(next: BillingFilter) {
    setFilter(next);
    requestAnimationFrame(() => {
      const heading = document.getElementById("charges-heading");
      if (heading && heading.getBoundingClientRect().top < 100) heading.scrollIntoView({ block: "start" });
    });
  }

  function retry() {
    fees.refetch();
    casesQuery.refetch();
  }

  const searching = query.trim().length > 0;

  return (
    <div className="px-4 sm:px-7 pt-4 sm:pt-7 pb-[60px] max-w-[1100px] mx-auto space-y-5 max-md:space-y-3.5">
      {/* The filter is pinned under the phone's top bar, so it stays in reach
          while reading down a long list. */}
      {isMobile && !loading && !failed && (
        <MobileSubbar height={44}>
          <BillingFilterTabs summary={summary} active={filter} onChange={changeFilterFromTabs} />
        </MobileSubbar>
      )}
      {/* space-y-5 already spaces the strip from the header. */}
      <SectionTabs tabs={BILLING_TABS} className="mb-0" />
      <div className="max-md:animate-rise-in motion-reduce:animate-none">
        <h1 className="text-page-title max-md:!text-[26px] max-md:!leading-[1.1] text-gray-900 mb-1.5 max-md:mb-1">Billing</h1>
        <p className="text-sm text-gray-600">
          Who owes what, which invoices are overdue, and hearings not yet billed.
        </p>
      </div>

      {loading ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading billing">
          <Skeleton className="h-28 rounded-xl" />
          <Skeleton className="h-12 rounded-lg" />
          <Skeleton className="h-56 rounded-xl" />
        </div>
      ) : failed ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-sm text-status-alert">Could not load billing. Try refreshing the page.</p>
            <Button variant="secondary" size="sm" className="mt-3" onClick={retry}>
              Try again
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="max-md:animate-rise-in motion-reduce:animate-none" style={staggerDelay(1)}>
            {isMobile ? (
              <SummaryHero summary={summary} />
            ) : (
              <SummaryTiles summary={summary} active={filter} onChange={setFilter} />
            )}
          </div>

          <div
            role="search"
            className="flex h-12 items-center gap-2.5 rounded-lg border border-gray-200 bg-surface px-3 focus-within:border-[var(--ci-ink)] md:h-10"
          >
            <Search className="h-[18px] w-[18px] flex-shrink-0 text-gray-400" strokeWidth={1.8} aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search client, case or invoice number"
              aria-label="Search charges"
              enterKeyHint="search"
              className="min-w-0 flex-1 bg-transparent text-sm text-gray-800 outline-none placeholder:text-gray-400 [&::-webkit-search-cancel-button]:hidden"
            />
            {query && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={() => setQuery("")}
                className="flex h-8 w-8 flex-shrink-0 animate-pop-in items-center justify-center rounded-full bg-gray-100 text-gray-500 motion-reduce:animate-none"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>

          <section aria-labelledby="charges-heading" className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <h2 id="charges-heading" className="scroll-mt-28 text-card-title text-gray-900">
                {HEADINGS[filter]}
              </h2>
              <span className="text-sm text-gray-500" aria-live="polite">
                {pluralize(matched.length, "charge")}
                {filter !== "open" && (
                  <>
                    {" · "}
                    <button type="button" onClick={() => setFilter("open")} className="underline">
                      show all unpaid
                    </button>
                  </>
                )}
              </span>
            </div>

            {groups.length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-sm text-gray-500">
                  {searching ? (
                    <>
                      No charges match &ldquo;{query.trim()}&rdquo; here.{" "}
                      <button type="button" onClick={() => setQuery("")} className="underline">
                        Clear the search
                      </button>
                    </>
                  ) : rows.length === 0 ? (
                    <>
                      No charges recorded yet. Record a fee from a hearing, or from the hearings not yet
                      billed below.{" "}
                      {clients.length === 0 && (
                        <>
                          Link cases to <Link href="/clients" className="underline">clients</Link> to get
                          per-client statements.
                        </>
                      )}
                    </>
                  ) : (
                    EMPTY[filter]
                  )}
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {groups.map((group, i) => (
                  <FeeGroupCard
                    key={group.key}
                    group={group}
                    filter={filter}
                    clients={clients}
                    index={i}
                    onMarkPaid={(markRows) => setSheet({ rows: markRows, open: true })}
                    onStatement={openStatement}
                    statementBusy={viewStatement.isPending && viewStatement.variables === group.clientId}
                    onAssign={assign}
                  />
                ))}
              </div>
            )}

            {filter === "paid" && matched.length > shown.length && (
              <div className="text-center">
                <Button variant="secondary" size="sm" onClick={() => setShowAllPaid(true)}>
                  Show {matched.length - shown.length} older
                </Button>
              </div>
            )}
          </section>

          <Card className="max-md:animate-rise-in motion-reduce:animate-none" style={staggerDelay(2)}>
            <CardHeader>
              <CardTitle>This month&apos;s hearings not yet billed</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {portfolio.isLoading ? (
                <Skeleton className="h-16 rounded-lg" />
              ) : portfolio.data ? (
                <>
                  <UnbilledHearings rows={portfolio.data.uninvoiced_hearings} />
                  {portfolio.data.uninvoiced_hearings_total > portfolio.data.uninvoiced_hearings.length && (
                    <p className="text-xs text-gray-500">
                      Showing {portfolio.data.uninvoiced_hearings.length} of{" "}
                      {portfolio.data.uninvoiced_hearings_total}.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-status-alert">Could not load the hearings not yet billed.</p>
              )}
            </CardContent>
          </Card>

          <Card className="max-md:animate-rise-in motion-reduce:animate-none" style={staggerDelay(3)}>
            <CardHeader className="flex flex-row flex-wrap items-baseline justify-between gap-2">
              <CardTitle>Unpaid invoices by age</CardTitle>
              <span className="text-sm text-gray-600">
                {pluralize(summary.awaiting.count, "invoice")} awaiting payment
              </span>
            </CardHeader>
            <CardContent>
              <AgingBuckets buckets={aging} />
            </CardContent>
          </Card>
        </>
      )}

      <MarkPaidSheet
        rows={sheet.rows}
        open={sheet.open}
        onClose={() => setSheet((s) => ({ ...s, open: false }))}
      />
    </div>
  );
}
