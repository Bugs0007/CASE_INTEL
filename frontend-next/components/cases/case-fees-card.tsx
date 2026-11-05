"use client";

import { useState } from "react";
import { IndianRupee, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ExpandableCard } from "@/components/ui/expandable-card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { showToast } from "@/components/ui/toaster";
import {
  CATEGORY_OPTIONS,
  ChargeRow,
  errorDetail,
} from "@/components/hearings/hearing-billing-actions";
import { useAdvocateProfile, useCreateFee } from "@/hooks/use-billing";
import {
  flattenFees,
  matchesQuery,
  previewFees,
  sortFees,
  splitHearings,
} from "@/lib/case-previews";
import { formatHearingDate, formatINR } from "@/lib/utils";
import type { CaseFeeSummary, FeeCategory, Hearing } from "@/types";

interface CaseFeesCardProps {
  caseId: number;
  summary: CaseFeeSummary;
  hearings: Hearing[];
}

/** What is owed on this case. Unpaid charges first (the longest outstanding
 * at the top), then the latest paid; each keeps the invoice lifecycle it has
 * on its hearing card (generate, send, mark paid, view PDF).
 *
 * Fees are recorded against a hearing, so the list is built from the
 * hearings the page already loaded. */
export function CaseFeesCard({ caseId, summary, hearings }: CaseFeesCardProps) {
  const fees = flattenFees(hearings);
  const previewed = previewFees(fees);
  const { data: profile } = useAdvocateProfile();
  // Undefined while the profile loads -- don't withhold Send before we know.
  const canSend = !(profile !== undefined && !profile.contact_email);
  const [recording, setRecording] = useState(false);

  const actions =
    hearings.length > 0 && !recording ? (
      <Button variant="secondary" size="sm" onClick={() => setRecording(true)}>
        <Plus className="h-4 w-4" />
        Record fee
      </Button>
    ) : null;

  return (
    <ExpandableCard
      title="Fees & billing"
      icon={<IndianRupee className="h-4 w-4" />}
      count={fees.length}
      actions={actions}
      viewAll={{ total: fees.length, shown: previewed.length }}
      expandable={fees.length > 0}
      bodyClassName="space-y-3"
    >
      {({ expanded, isOpen, query }) => {
        const showForm = expanded === isOpen;
        const visible = (expanded ? sortFees(fees) : previewed).filter(
          ({ fee, hearing }) =>
            !expanded ||
            matchesQuery(
              query,
              fee.category_display,
              fee.status_display,
              fee.invoice_number,
              formatHearingDate(hearing.hearing_date),
            ),
        );

        return (
          <>
            <FeeSummaryStrip summary={summary} />

            {showForm && recording && (
              <RecordFeeForm caseId={caseId} hearings={hearings} onDone={() => setRecording(false)} />
            )}

            {fees.length === 0 ? (
              <p className="text-sm text-gray-500">
                {hearings.length === 0
                  ? "Fees are recorded against a hearing. Add a hearing first."
                  : "No fees recorded on this case."}
              </p>
            ) : visible.length === 0 ? (
              <p className="text-sm text-gray-500">No fees match.</p>
            ) : (
              <ul className="space-y-3">
                {visible.map(({ fee, hearing }) => (
                  <li key={fee.id}>
                    <div className="mb-1 flex items-center justify-between gap-2 text-xs text-gray-500">
                      <span className="font-mono">{formatHearingDate(hearing.hearing_date)}</span>
                      <span className="truncate">{hearing.hearing_type_display}</span>
                    </div>
                    <ul aria-label="Charges">
                      <ChargeRow fee={fee} caseId={caseId} canSend={canSend} />
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </>
        );
      }}
    </ExpandableCard>
  );
}

/** Outstanding, and where the rest sits. The totals come from the case
 * itself, so they stay right even for charges beyond the preview. */
function FeeSummaryStrip({ summary }: { summary: CaseFeeSummary }) {
  const buckets = [
    {
      label: "Pending",
      hint: "Recorded but not yet invoiced",
      amount: summary.pending_amount,
      count: summary.pending_count,
      className: "text-status-pending",
    },
    {
      label: "Invoiced",
      hint: "Billed, awaiting payment",
      amount: summary.invoiced_amount,
      count: summary.invoiced_count,
      className: "text-status-pending",
    },
    {
      label: "Paid",
      hint: "Received",
      amount: summary.paid_amount,
      count: summary.paid_count,
      className: "text-status-ok",
    },
  ];

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-gray-400">Outstanding</span>
        <span className="text-sm font-semibold text-gray-900">
          {formatINR(summary.outstanding_amount ?? 0)}
        </span>
      </div>
      <dl className="grid grid-cols-3 gap-2">
        {buckets.map((bucket) => (
          <div key={bucket.label} className="min-w-0">
            <dt className="text-xs text-gray-400" title={bucket.hint}>
              {bucket.label} ({bucket.count ?? 0})
            </dt>
            <dd className={`truncate text-sm font-semibold ${bucket.className}`}>
              {formatINR(bucket.amount ?? 0)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

interface RecordFeeFormProps {
  caseId: number;
  hearings: Hearing[];
  onDone: () => void;
}

/** Record a charge against one of this case's hearings. Billing happens
 * after a hearing is heard, so the most recent past hearing is the default. */
function RecordFeeForm({ caseId, hearings, onDone }: RecordFeeFormProps) {
  const { upcoming, past } = splitHearings(hearings);
  const ordered = [...past, ...upcoming];
  const [hearingId, setHearingId] = useState<number>((past[0] ?? upcoming[0] ?? hearings[0]).id);
  const [category, setCategory] = useState<FeeCategory>("appearance");
  const [amount, setAmount] = useState("");
  const createFee = useCreateFee(caseId);

  async function handleAdd() {
    const trimmed = amount.trim();
    // Only an appearance fee has a default amount (the profile's
    // default_fee_amount, applied by the server).
    if (category !== "appearance" && !trimmed) {
      showToast.error(
        "Enter an amount",
        "Only an appearance fee has a default amount. Enter what this charge costs.",
      );
      return;
    }
    try {
      await createFee.mutateAsync({
        hearing: hearingId,
        category,
        ...(trimmed ? { amount: trimmed } : {}),
      });
      showToast.success("Charge added", "Generate an invoice when you're ready to bill it.");
      onDone();
    } catch (error) {
      showToast.error("Could not add the charge", errorDetail(error, "Please try again."));
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-gray-100 p-2.5">
      <div className="w-full">
        <Select
          value={hearingId}
          onChange={(e) => setHearingId(Number(e.target.value))}
          aria-label="Hearing"
          className="h-11 md:h-8 py-0 text-sm"
        >
          {ordered.map((hearing) => (
            <option key={hearing.id} value={hearing.id}>
              {formatHearingDate(hearing.hearing_date)} · {hearing.hearing_type_display}
            </option>
          ))}
        </Select>
      </div>
      <Select
        value={category}
        onChange={(e) => setCategory(e.target.value as FeeCategory)}
        aria-label="Charge category"
        className="h-11 md:h-8 w-40 py-0 text-sm"
      >
        {CATEGORY_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </Select>
      <Input
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
        placeholder="Amount"
        inputMode="decimal"
        aria-label="Charge amount"
        className="h-11 md:h-8 w-32 text-sm"
      />
      <Button size="sm" onClick={handleAdd} disabled={createFee.isPending}>
        {createFee.isPending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Plus className="h-4 w-4" />
        )}
        Add charge
      </Button>
      <Button variant="ghost" size="sm" onClick={onDone}>
        Cancel
      </Button>
    </div>
  );
}
