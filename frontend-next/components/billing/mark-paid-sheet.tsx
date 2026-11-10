"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import { errorDetail } from "@/components/hearings/hearing-billing-actions";
import { useMarkFeesPaid } from "@/hooks/use-billing";
import { caseLabel, fromPaise, type FeeRow } from "@/lib/billing-model";
import { formatINR } from "@/lib/utils";

interface MarkPaidSheetProps {
  /** The invoiced charges to settle: one, or all of a client's. */
  rows: FeeRow[];
  open: boolean;
  onClose: () => void;
}

function Line({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5">
      <dt className="flex-shrink-0 text-sm text-gray-500">{label}</dt>
      <dd className="min-w-0 break-words text-right text-sm text-gray-900">{children}</dd>
    </div>
  );
}

/** The confirmation before a charge is marked paid.
 *
 * Marking paid changes the books and has no undo (the server only moves a fee
 * forward: pending -> invoiced -> paid), so nothing is sent until the advocate
 * has read who, which case, which invoice and how much, and pressed the one
 * clear button. A bottom sheet on a phone, a centred dialog from md up.
 *
 * The server's own reason is shown when it refuses (not invoiced yet,
 * already paid), and the sheet stays open so it can be read. A batch that
 * only half went through is reported as such. */
export function MarkPaidSheet({ rows, open, onClose }: MarkPaidSheetProps) {
  const markPaid = useMarkFeesPaid();
  const [error, setError] = useState("");

  const single = rows.length === 1 ? rows[0] : null;
  const totalPaise = rows.reduce((sum, row) => sum + row.paise, 0);
  const total = formatINR(fromPaise(totalPaise));
  const clientName = rows[0]?.clientName || "Not linked to a client";

  function close() {
    setError("");
    onClose();
  }

  async function handleConfirm() {
    setError("");
    try {
      const outcome = await markPaid.mutateAsync(
        rows.map((row) => ({ feeId: row.fee.id, caseId: row.fee.case_id })),
      );
      if (outcome.failed.length === 0) {
        if (single) {
          showToast.success("Marked paid", `${single.fee.invoice_number} · ${total} is settled.`);
        } else {
          showToast.success(`Marked ${rows.length} paid`, `${total} from ${clientName} is settled.`);
        }
        close();
        return;
      }
      const message = errorDetail(outcome.failed[0].error, "Please try again.");
      if (outcome.paid.length === 0) {
        // 409 when the fee isn't invoiced yet or is already paid.
        setError(message);
        showToast.error("Could not mark it paid", message);
        return;
      }
      showToast.warning(`Marked ${outcome.paid.length} of ${rows.length} paid`, message);
      close();
    } catch (e) {
      const message = errorDetail(e, "Please try again.");
      setError(message);
      showToast.error("Could not mark it paid", message);
    }
  }

  return (
    <BottomSheet
      open={open}
      onClose={close}
      label={single ? "Mark as paid" : "Mark invoices as paid"}
      title={single ? "Mark as paid?" : `Mark ${rows.length} invoices paid?`}
      footer={
        <div className="flex gap-2 px-4 py-3">
          <Button variant="secondary" size="lg" className="flex-1 !px-3" onClick={close} disabled={markPaid.isPending}>
            Cancel
          </Button>
          <Button size="lg" className="flex-[1.6] !px-3" onClick={handleConfirm} disabled={markPaid.isPending || rows.length === 0}>
            {markPaid.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {single ? `Mark paid · ${total}` : `Mark ${rows.length} paid · ${total}`}
          </Button>
        </div>
      }
    >
      <div className="px-4 py-3">
        {single ? (
          <dl className="divide-y divide-gray-100">
            <Line label="Client">{clientName}</Line>
            <Line label="Case">{caseLabel(single)}</Line>
            <Line label="Invoice">
              {single.fee.invoice_number}
              <span className="block text-xs text-gray-500">{single.fee.category_display}</span>
            </Line>
            <Line label="Amount">
              <span className="font-mono text-[22px] font-semibold">{total}</span>
            </Line>
          </dl>
        ) : (
          <>
            <p className="mb-1 text-sm text-gray-500">{clientName}</p>
            <ul className="max-h-[40dvh] divide-y divide-gray-100 overflow-y-auto" aria-label="Invoices to mark paid">
              {rows.map((row) => (
                <li key={row.fee.id} className="flex items-baseline justify-between gap-3 py-2.5">
                  <span className="min-w-0 text-sm text-gray-900">
                    {row.fee.invoice_number}
                    <span className="block truncate text-xs text-gray-500">{caseLabel(row)}</span>
                  </span>
                  <span className="flex-shrink-0 font-mono text-sm">{formatINR(fromPaise(row.paise))}</span>
                </li>
              ))}
            </ul>
            <div className="flex items-baseline justify-between border-t border-gray-200 pt-3">
              <span className="text-sm font-medium text-gray-700">Total</span>
              <span className="font-mono text-[22px] font-semibold text-gray-900">{total}</span>
            </div>
          </>
        )}
        <p className="mt-3 text-sm text-gray-600">
          {single
            ? "This records that you have received the payment. It can't be undone."
            : `This records that you have received all ${rows.length} payments. It can't be undone.`}
        </p>
        {error && (
          <p role="alert" className="mt-3 rounded-md bg-status-alert-soft px-3 py-2 text-sm text-status-alert">
            {error}
          </p>
        )}
      </div>
    </BottomSheet>
  );
}
