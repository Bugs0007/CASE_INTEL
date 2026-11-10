"use client";

import Link from "next/link";
import { FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import { errorDetail } from "@/components/hearings/hearing-billing-actions";
import { useGenerateInvoice, useViewInvoice } from "@/hooks/use-billing";
import { feeChip, fromPaise, invoicedWords, type FeeRow } from "@/lib/billing-model";
import { dayMonth } from "@/lib/dashboard/dates";
import { cn, formatINR, hasPlaceholderTitle, staggerDelay } from "@/lib/utils";

interface FeeRowItemProps {
  row: FeeRow;
  /** Open the confirmation for marking this one charge paid. */
  onMarkPaid: (rows: FeeRow[]) => void;
  index?: number;
}

/** One charge on the Billing page, with the one action it can take right now:
 * pending -> Generate invoice, invoiced -> Mark paid, paid -> nothing (just
 * the date and the invoice PDF). Mirrors the hearing's ChargeRow: the same
 * hooks, toasts and server messages, and no button for a step the server
 * would refuse. Its own component, so a spinner shows on this row only. */
export function FeeRowItem({ row, onMarkPaid, index = 0 }: FeeRowItemProps) {
  const { fee } = row;
  const generateInvoice = useGenerateInvoice(fee.case_id);
  const viewInvoice = useViewInvoice();
  const chip = feeChip(row);
  const showTitle = !hasPlaceholderTitle({ title: row.caseTitle, cnr_number: null, case_number: row.caseNumber });
  const caseName = row.caseNumber || row.caseTitle;

  async function handleGenerate() {
    try {
      const updated = await generateInvoice.mutateAsync(fee.id);
      showToast.success(
        `Invoice ${updated.invoice_number} generated`,
        "Open the PDF here, or send it from the case's Fees tab.",
      );
    } catch (error) {
      showToast.error("Could not generate the invoice", errorDetail(error, "Please try again."));
    }
  }

  function handleView() {
    viewInvoice.mutate(fee.id, {
      onError: (error) =>
        showToast.error("Could not open the invoice", errorDetail(error, "Please try again.")),
    });
  }

  const meta: string[] = [];
  if (fee.status === "pending") {
    meta.push(`Hearing ${dayMonth(row.hearingDay)}`, "no invoice yet");
  } else {
    meta.push(fee.invoice_number);
    if (fee.status === "invoiced" && row.ageDays !== null) {
      meta.push(invoicedWords(row.ageDays).toLowerCase());
      if (fee.send_status !== "sent") meta.push("not emailed");
    } else if (row.paidDay) {
      meta.push(`paid ${dayMonth(row.paidDay)}`);
    }
  }

  return (
    <li
      data-testid="fee-row"
      data-status={fee.status}
      style={staggerDelay(index, 35, 8)}
      className="animate-rise-in border-b border-gray-100 px-4 py-3 last:border-0 motion-reduce:animate-none md:flex md:items-center md:gap-4 md:px-5 md:py-2.5"
    >
      <div className="flex items-start gap-3 md:min-w-0 md:flex-1 md:items-center">
        <div className="min-w-0 flex-1">
          <Link
            href={`/cases/${fee.case_id}`}
            className="block truncate text-sm font-medium text-gray-900 hover:underline"
          >
            {caseName}
          </Link>
          <div className="truncate text-xs text-gray-500">
            {fee.category_display}
            {showTitle && row.caseNumber ? ` · ${row.caseTitle}` : ""}
          </div>
          <div className="mt-0.5 text-xs text-gray-500">{meta.join(" · ")}</div>
        </div>
        <div className="flex-shrink-0 text-right md:flex md:items-center md:gap-3">
          <div className="font-mono text-[15px] font-semibold text-gray-900 md:w-24">{formatINR(fromPaise(row.paise))}</div>
          <span className={cn("ci-chip mt-1 inline-block md:mt-0 md:w-[132px] md:text-center", `ci-chip--${chip.tone}`)}>{chip.text}</span>
        </div>
      </div>

      <div className="mt-2.5 flex gap-2 md:mt-0 md:w-[220px] md:flex-shrink-0 md:justify-end">
        {fee.status === "pending" && (
          <Button
            size="sm"
            className="max-md:flex-1"
            onClick={handleGenerate}
            disabled={generateInvoice.isPending}
            aria-label={`Generate invoice for ${caseName}, ${fee.category_display}`}
          >
            {generateInvoice.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
            Generate invoice
          </Button>
        )}
        {fee.status === "invoiced" && (
          <Button
            size="sm"
            className="max-md:flex-1"
            onClick={() => onMarkPaid([row])}
            aria-label={`Mark ${fee.invoice_number} paid`}
          >
            Mark paid
          </Button>
        )}
        {fee.status !== "pending" && (
          <Button
            variant="secondary"
            size="sm"
            onClick={handleView}
            disabled={viewInvoice.isPending}
            title="Open the invoice PDF in a new tab"
            aria-label={`View PDF ${fee.invoice_number}`}
          >
            {viewInvoice.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
            PDF
          </Button>
        )}
      </div>
    </li>
  );
}
