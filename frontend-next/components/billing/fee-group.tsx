"use client";

import Link from "next/link";
import { FileDown, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { FeeRowItem } from "@/components/billing/fee-row";
import { fromPaise, type BillingFilter, type FeeGroup, type FeeRow } from "@/lib/billing-model";
import { cn, formatINR, staggerDelay } from "@/lib/utils";
import type { Client } from "@/types";

interface FeeGroupCardProps {
  group: FeeGroup;
  filter: BillingFilter;
  /** The advocate's clients, for assigning an unlinked case to one. */
  clients: Client[];
  onMarkPaid: (rows: FeeRow[]) => void;
  onStatement: (clientId: number) => void;
  statementBusy: boolean;
  onAssign: (caseId: number, clientId: number) => void;
  index?: number;
}

/** One client's charges (or, for a case with no client, that case's): who it
 * is and how much is unpaid on top, "Mark N paid" and Statement beside it,
 * then each charge as a row. */
export function FeeGroupCard({
  group,
  filter,
  clients,
  onMarkPaid,
  onStatement,
  statementBusy,
  onAssign,
  index = 0,
}: FeeGroupCardProps) {
  const paidView = filter === "paid";
  const money = paidView ? group.paidPaise : group.unpaidPaise;
  const overdue = group.oldestDays !== null && group.oldestDays > 30;

  return (
    <section
      aria-label={group.title}
      data-testid="fee-group"
      style={staggerDelay(index, 50, 6)}
      className="ci-card animate-rise-in overflow-hidden motion-reduce:animate-none"
    >
      <header className="flex flex-wrap items-start gap-x-3 gap-y-2.5 border-b border-gray-100 px-4 pb-3 pt-3.5 md:flex-nowrap md:items-center md:px-5">
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[15px] font-semibold text-gray-900">
            {group.clientId === null && group.caseId !== null ? (
              <Link href={`/cases/${group.caseId}`} className="hover:underline">
                {group.title}
              </Link>
            ) : (
              group.title
            )}
          </h3>
          <p className="truncate text-xs text-gray-500">
            {group.subtitle}
            {group.clientType === "business" ? " · business" : ""}
            {group.clientId === null && " · not linked to a client"}
          </p>
        </div>
        <div className="flex-shrink-0 text-right md:order-3 md:w-24">
          <div className="font-mono text-[15px] font-semibold text-gray-900">{formatINR(fromPaise(money))}</div>
          <div className="text-[11px] text-gray-500">{paidView ? "paid" : "unpaid"}</div>
        </div>

        {/* On a phone: its own line under the name. On a desktop: between the
            name and the total, so the header is one row. */}
        <div className="flex basis-full flex-wrap items-center gap-2 empty:hidden md:order-2 md:basis-auto md:justify-end">
          {group.oldestDays !== null && !paidView && (
            <span className={cn("ci-chip inline-block", overdue ? "ci-chip--alert" : "ci-chip--none")}>
              oldest invoice {group.oldestDays} d
            </span>
          )}
          {group.invoiced.length >= 2 && (
            <Button size="sm" onClick={() => onMarkPaid(group.invoiced)}>
              Mark all {group.invoiced.length} paid
            </Button>
          )}
          {group.clientId !== null && !paidView && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onStatement(group.clientId!)}
              disabled={statementBusy}
              aria-label={`Statement for ${group.title}`}
            >
              {statementBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileDown className="h-4 w-4" />}
              Statement
            </Button>
          )}
          {group.clientId === null &&
            group.caseId !== null &&
            (clients.length > 0 ? (
              <div className="w-full md:w-56">
                <Select
                  aria-label={`Assign ${group.title} to a client`}
                  className="h-11 md:h-10"
                  value=""
                  onChange={(e) => e.target.value && onAssign(group.caseId!, Number(e.target.value))}
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
            ))}
        </div>
      </header>

      <ul aria-label={`${group.title} charges`}>
        {group.rows.map((row, i) => (
          <FeeRowItem key={row.fee.id} row={row} onMarkPaid={onMarkPaid} index={i} />
        ))}
      </ul>
    </section>
  );
}
