"use client";

import { useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showToast } from "@/components/ui/toaster";
import { billingPortfolioKeys } from "@/hooks/use-clients";
import { useAdvocateProfile, useCreateFee } from "@/hooks/use-billing";
import { apiErrorDetail } from "@/lib/api/client";
import { formatHearingDate, formatINR, hasPlaceholderTitle } from "@/lib/utils";
import type { UninvoicedHearing } from "@/types";

interface CaseGroup {
  caseId: number;
  caseNumber: string;
  caseTitle: string;
  hearings: UninvoicedHearing[];
}

function groupByCase(rows: UninvoicedHearing[]): CaseGroup[] {
  const groups = new Map<number, CaseGroup>();
  for (const row of rows) {
    const group = groups.get(row.case_id) ?? {
      caseId: row.case_id,
      caseNumber: row.case_number,
      caseTitle: row.case_title,
      hearings: [],
    };
    group.hearings.push(row);
    groups.set(row.case_id, group);
  }
  return [...groups.values()];
}

/** This month's hearings that were heard but not billed, grouped by case,
 * each with the fee recorded right here -- prefilled with the default
 * appearance fee -- instead of a trip to the case page per hearing. */
export function UnbilledHearings({ rows }: { rows: UninvoicedHearing[] }) {
  const { data: profile } = useAdvocateProfile();
  const defaultFee = Number(profile?.default_fee_amount ?? 0) > 0 ? String(Number(profile!.default_fee_amount)) : "";

  if (rows.length === 0) {
    return <p className="text-sm text-gray-500">Every hearing so far this month has been invoiced.</p>;
  }

  return (
    <div className="space-y-3">
      {groupByCase(rows).map((group) => (
        <section key={group.caseId} className="rounded-lg border border-gray-100">
          <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-gray-100 px-3 py-2">
            <Link href={`/cases/${group.caseId}`} className="font-medium text-gray-900 hover:underline">
              {group.caseNumber}
            </Link>
            {!hasPlaceholderTitle({ title: group.caseTitle, cnr_number: null, case_number: group.caseNumber }) && (
              <span className="min-w-0 truncate text-xs text-gray-500">{group.caseTitle}</span>
            )}
          </header>
          <ul className="divide-y divide-gray-50">
            {group.hearings.map((hearing) => (
              <UnbilledRow key={hearing.hearing_id} hearing={hearing} defaultFee={defaultFee} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function UnbilledRow({ hearing, defaultFee }: { hearing: UninvoicedHearing; defaultFee: string }) {
  // null until typed in: the default fee arrives with the profile, which
  // can load after this row first renders.
  const [typed, setTyped] = useState<string | null>(null);
  const amount = typed ?? defaultFee;
  const createFee = useCreateFee(hearing.case_id);
  const queryClient = useQueryClient();

  async function handleRecord() {
    const trimmed = amount.trim();
    if (!trimmed || !(Number(trimmed) > 0)) {
      showToast.error("Enter an amount", "Set a default fee in Settings to have it filled in.");
      return;
    }
    try {
      await createFee.mutateAsync({ hearing: hearing.hearing_id, category: "appearance", amount: trimmed });
      queryClient.invalidateQueries({ queryKey: billingPortfolioKeys.all });
      showToast.success("Fee recorded", `${formatINR(trimmed)} for ${formatHearingDate(hearing.hearing_date)}.`);
    } catch (error) {
      showToast.error("Could not record the fee", apiErrorDetail(error, "Please try again."));
    }
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
      <span className="text-sm text-gray-800">{formatHearingDate(hearing.hearing_date)}</span>
      {hearing.has_fee ? (
        <span className="ci-chip ci-chip--pending">{formatINR(hearing.pending_amount)} not invoiced</span>
      ) : (
        <div className="flex items-center gap-2">
          <Input
            value={amount}
            onChange={(e) => setTyped(e.target.value)}
            inputMode="decimal"
            placeholder="Amount"
            aria-label={`Fee for the hearing on ${formatHearingDate(hearing.hearing_date)}`}
            className="h-11 md:h-8 w-28 text-sm"
          />
          <Button size="sm" variant="secondary" onClick={handleRecord} disabled={createFee.isPending}>
            {createFee.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Record fee
          </Button>
        </div>
      )}
    </li>
  );
}
