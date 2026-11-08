"use client";

import Link from "next/link";
import { FileDown, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { showToast } from "@/components/ui/toaster";
import { AgingBuckets } from "@/components/billing/aging-buckets";
import { BILLING_TABS, SectionTabs } from "@/components/layout/section-tabs";
import {
  billingPortfolioKeys,
  useBillingPortfolio,
  useClients,
  useViewClientStatement,
} from "@/hooks/use-clients";
import { useUpdateCase } from "@/hooks/use-cases";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { apiErrorDetail } from "@/lib/api/client";
import { cn, formatINR, staggerDelay } from "@/lib/utils";
import { UnbilledHearings } from "@/components/billing/unbilled-hearings";
import { useQueryClient } from "@tanstack/react-query";

/** Billing across every case: how long invoices have been unpaid, who owes
 * what, and which of this month's hearings were never billed. */
export default function BillingPage() {
  const { data, isLoading, error } = useBillingPortfolio();
  const { data: clients = [] } = useClients();
  const viewStatement = useViewClientStatement();
  const updateCase = useUpdateCase();
  const queryClient = useQueryClient();
  const isMobile = useIsMobile();

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

  return (
    <div className="px-4 sm:px-7 pt-4 sm:pt-7 pb-[60px] max-w-[1100px] mx-auto space-y-5 max-md:space-y-3.5">
      {/* space-y-5 already spaces the strip from the header. */}
      <SectionTabs tabs={BILLING_TABS} className="mb-0" />
      <div className="max-md:animate-rise-in motion-reduce:animate-none">
        <h1 className="text-page-title max-md:!text-[26px] max-md:!leading-[1.1] text-gray-900 mb-1.5 max-md:mb-1">Billing</h1>
        <p className="text-sm text-gray-600">
          Unpaid invoices by age, outstanding per client, and hearings not yet billed.
        </p>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 rounded-xl" />
      ) : error || !data ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-status-alert">
            Could not load billing. Try refreshing the page.
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="max-md:animate-rise-in motion-reduce:animate-none" style={staggerDelay(1)}>
            <CardHeader className="flex flex-row flex-wrap items-baseline justify-between gap-2">
              <CardTitle>Awaiting payment</CardTitle>
              <span className="text-sm text-gray-600">
                {formatINR(data.totals.invoiced_amount)} across {data.totals.invoiced_count} invoice
                {data.totals.invoiced_count === 1 ? "" : "s"}
                {data.totals.pending_count > 0 &&
                  ` · ${formatINR(data.totals.pending_amount)} recorded but not yet invoiced`}
              </span>
            </CardHeader>
            <CardContent>
              <AgingBuckets buckets={data.aging} />
            </CardContent>
          </Card>

          <Card className="max-md:animate-rise-in motion-reduce:animate-none" style={staggerDelay(2)}>
            <CardHeader>
              <CardTitle>Outstanding by client</CardTitle>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              {data.clients.length > 0 && isMobile ? (
                // A phone has no room for a five-column table: one card per client.
                <ul>
                  {data.clients.map((row, i) => {
                    const busy = viewStatement.isPending && viewStatement.variables === row.client_id;
                    const old = row.oldest_invoice_days !== null && row.oldest_invoice_days > 30;
                    return (
                      <li
                        key={row.client_id}
                        style={staggerDelay(i, 50)}
                        className="animate-rise-in border-b border-gray-100 px-4 py-3 last:border-0 motion-reduce:animate-none"
                      >
                        <div className="flex items-start gap-2">
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-[15px] font-semibold text-gray-900">{row.client_name}</div>
                            <div className="text-xs text-gray-500">
                              {row.case_count} case{row.case_count === 1 ? "" : "s"}
                              {row.client_type === "business" ? " · business" : ""}
                            </div>
                          </div>
                          {row.oldest_invoice_days !== null && (
                            <span className={cn("ci-chip flex-shrink-0", old ? "ci-chip--pending" : "ci-chip--none")}>
                              oldest {row.oldest_invoice_days} d
                            </span>
                          )}
                        </div>
                        <dl className="mt-2 grid grid-cols-2 gap-3">
                          <div>
                            <dt className="text-[11px] text-gray-500">Invoiced, unpaid</dt>
                            <dd className="font-mono text-[15px] font-semibold text-gray-900">{formatINR(row.invoiced_amount)}</dd>
                          </div>
                          <div>
                            <dt className="text-[11px] text-gray-500">Not yet invoiced</dt>
                            <dd className="font-mono text-[15px] text-gray-600">{formatINR(row.pending_amount)}</dd>
                          </div>
                        </dl>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="mt-2.5 w-full"
                          onClick={() => openStatement(row.client_id)}
                          disabled={busy}
                        >
                          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
                          Statement
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              ) : data.clients.length === 0 ? (
                <p className="px-5 py-6 text-sm text-gray-500">
                  No client has anything outstanding.{" "}
                  {clients.length === 0 && (
                    <>
                      Link cases to <Link href="/clients" className="underline">clients</Link> to get
                      per-client statements.
                    </>
                  )}
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-gray-500 border-b border-gray-100">
                    <tr>
                      <th className="px-5 py-2 font-medium">Client</th>
                      <th className="px-3 py-2 font-medium text-right">Invoiced, unpaid</th>
                      <th className="px-3 py-2 font-medium text-right">Not yet invoiced</th>
                      <th className="px-3 py-2 font-medium text-right">Oldest</th>
                      <th className="px-5 py-2" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.clients.map((row) => (
                      <tr key={row.client_id} className="border-b border-gray-50">
                        <td className="px-5 py-2">
                          <div className="font-medium text-gray-900">{row.client_name}</div>
                          <div className="text-xs text-gray-500">
                            {row.case_count} case{row.case_count === 1 ? "" : "s"}
                            {row.client_type === "business" ? " · business" : ""}
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right font-mono">{formatINR(row.invoiced_amount)}</td>
                        <td className="px-3 py-2 text-right font-mono text-gray-600">
                          {formatINR(row.pending_amount)}
                        </td>
                        <td className="px-3 py-2 text-right text-gray-600">
                          {row.oldest_invoice_days !== null ? `${row.oldest_invoice_days} d` : "Unknown"}
                        </td>
                        <td className="px-5 py-2 text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openStatement(row.client_id)}
                            disabled={viewStatement.isPending && viewStatement.variables === row.client_id}
                          >
                            {viewStatement.isPending && viewStatement.variables === row.client_id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <FileDown className="h-4 w-4" />
                            )}
                            Statement
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {data.clients_total > data.clients.length && (
                <p className="px-5 py-2 text-xs text-gray-500">
                  Showing {data.clients.length} of {data.clients_total} clients.
                </p>
              )}
            </CardContent>
          </Card>

          {data.unassigned.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Cases not linked to a client</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-xs text-gray-500">
                  Money is owed on these cases but they aren&apos;t linked to a client, so they
                  can&apos;t appear on a client statement.
                </p>
                {data.unassigned.map((row) => (
                  <div key={row.case_id} className="flex flex-wrap items-center gap-3 rounded-lg border border-gray-100 px-3 py-2">
                    <div className="flex-1 min-w-[200px]">
                      <Link href={`/cases/${row.case_id}`} className="font-medium text-gray-900 hover:underline">
                        {row.case_number}
                      </Link>
                      <div className="text-xs text-gray-500 truncate">
                        {row.case_title}
                        {row.client_name ? ` · ${row.client_name}` : ""}
                      </div>
                    </div>
                    <div className="text-right font-mono text-sm">
                      {formatINR(row.invoiced_amount)}
                      {Number(row.pending_amount) > 0 && (
                        <div className="text-xs text-gray-500">+ {formatINR(row.pending_amount)} not invoiced</div>
                      )}
                    </div>
                    {clients.length > 0 ? (
                      <div className="w-48">
                        <Select
                          aria-label={`Assign ${row.case_number} to a client`}
                          value=""
                          onChange={(e) => e.target.value && assign(row.case_id, Number(e.target.value))}
                        >
                          <option value="">Assign client…</option>
                          {clients.map((c) => (
                            <option key={c.id} value={c.id}>
                              {c.name}
                            </option>
                          ))}
                        </Select>
                      </div>
                    ) : (
                      <Link href="/clients" className="text-xs underline">
                        Add a client
                      </Link>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>This month&apos;s hearings not yet billed</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <UnbilledHearings rows={data.uninvoiced_hearings} />
              {data.uninvoiced_hearings_total > data.uninvoiced_hearings.length && (
                <p className="text-xs text-gray-500">
                  Showing {data.uninvoiced_hearings.length} of {data.uninvoiced_hearings_total}.
                </p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
