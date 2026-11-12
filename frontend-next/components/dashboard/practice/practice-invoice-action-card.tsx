"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { PracticeActionCard } from "@/types/practice";
import { caseHref } from "./routes";
import Link from "next/link";

export interface PracticeInvoiceActionCardProps {
  card: PracticeActionCard;
  /** The case's title, when the turn's sources name it. */
  caseTitle?: string | null;
  confirming?: boolean;
  onConfirm: (feeId: number) => void;
  onDismiss: () => void;
}

/** A proposed invoice email. Nothing is sent by rendering it: the advocate
 * presses "Send invoice", then confirms the named recipient. With any blocker
 * present there is no control to send at all. */
export function PracticeInvoiceActionCard({
  card,
  caseTitle,
  confirming = false,
  onConfirm,
  onDismiss,
}: PracticeInvoiceActionCardProps) {
  const blocked = card.blockers.length > 0;
  const [asking, setAsking] = useState(false);
  // Held from the first Confirm click until the send settles, so a double
  // click cannot send twice before the parent re-renders.
  const locked = useRef(false);
  const wasConfirming = useRef(false);
  useEffect(() => {
    if (wasConfirming.current && !confirming) locked.current = false;
    wasConfirming.current = confirming;
  }, [confirming]);

  function confirm() {
    if (locked.current) return;
    locked.current = true;
    onConfirm(card.fee_id);
  }

  const recipient = [card.recipient_name, card.recipient_email].filter(Boolean).join(", ");
  return (
    <section aria-label="Invoice to send" className="space-y-2 rounded-lg border border-gray-200 bg-surface p-3">
      <h4 className="text-sm font-semibold text-gray-900">Send invoice by email</h4>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        <dt className="text-gray-500">Invoice</dt>
        <dd className="break-words text-gray-900">{card.invoice_number ?? "Not generated yet"}</dd>
        <dt className="text-gray-500">Amount</dt>
        <dd className="text-gray-900">{card.amount}</dd>
        <dt className="text-gray-500">To</dt>
        <dd className="break-words text-gray-900">{recipient || "No recipient on file"}</dd>
        <dt className="text-gray-500">Case</dt>
        <dd className="break-words text-gray-900">
          <Link href={caseHref(card.case_id)} className="text-primary hover:underline">
            {caseTitle ?? `Case ${card.case_id}`}
          </Link>
        </dd>
      </dl>
      {blocked && (
        <div role="alert" className="rounded-lg bg-amber-50 p-2 text-sm text-amber-900">
          <p className="font-medium">This invoice cannot be sent yet.</p>
          <ul className="list-disc pl-5">
            {card.blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      )}
      {!blocked && asking && (
        <p role="group" aria-label="Confirm sending" className="text-sm text-gray-900">
          {`Send invoice ${card.invoice_number} to ${card.recipient_email}?`}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {!blocked && !asking && (
          <Button type="button" size="sm" onClick={() => setAsking(true)}>
            Send invoice
          </Button>
        )}
        {!blocked && asking && (
          <>
            <Button type="button" size="sm" disabled={confirming} onClick={confirm}>
              Confirm
            </Button>
            <Button type="button" variant="secondary" size="sm" disabled={confirming} onClick={() => setAsking(false)}>
              Cancel
            </Button>
          </>
        )}
        <Button type="button" variant="ghost" size="sm" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </section>
  );
}
