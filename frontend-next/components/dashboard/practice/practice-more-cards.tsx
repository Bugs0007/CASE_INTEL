"use client";

import { useId, useState } from "react";
import { Input } from "@/components/ui/input";
import { apiErrorDetail } from "@/lib/api/client";
import type { PracticeCardActions } from "@/hooks/use-practice-card-actions";
import { formatINR } from "@/lib/utils";
import type {
  PracticeBulkCreateFeesCard,
  PracticeBulkSendInvoicesCard,
  PracticeCreateTaskCard,
  PracticeMarkPaidCard,
} from "@/types/practice";
import { PracticeActionCardShell } from "./practice-action-card-shell";

interface CardProps<T> {
  card: T;
  actions: PracticeCardActions;
  onDismiss?: () => void;
}

const validAmount = (value: string) => value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) > 0;
const plural = (count: number, one: string, many = `${one}s`) => `${count} ${count === 1 ? one : many}`;

function Label({ htmlFor, children }: { htmlFor: string; children: string }) {
  return (
    <label htmlFor={htmlFor} className="text-xs font-medium text-gray-600">
      {children}
    </label>
  );
}

export function CreateTaskCard({ card, actions, onDismiss }: CardProps<PracticeCreateTaskCard>) {
  const id = useId();
  const [title, setTitle] = useState(card.title);
  const [due, setDue] = useState(card.due_date ?? "");

  return (
    <PracticeActionCardShell
      title="Add a task"
      caseId={card.case_id}
      caseTitle={card.case_title}
      blockers={card.blockers}
      actionLabel="Add task"
      question={card.case_id ? "Add this task to the case?" : "Add this task? It is not linked to a case."}
      ready={title.trim() !== ""}
      onDismiss={onDismiss}
      run={async () => {
        await actions.createTask({ case: card.case_id, title: title.trim(), due_date: due || null });
        return { text: "Task added. It shows in your deadlines and calendar." };
      }}
    >
      {(editable) => (
        <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
          <div className="space-y-1">
            <Label htmlFor={`${id}-title`}>Task</Label>
            <Input id={`${id}-title`} value={title} maxLength={255} disabled={!editable} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor={`${id}-due`}>Due date</Label>
            <Input id={`${id}-due`} type="date" value={due} disabled={!editable} onChange={(e) => setDue(e.target.value)} />
          </div>
        </div>
      )}
    </PracticeActionCardShell>
  );
}

export function MarkPaidCard({ card, actions, onDismiss }: CardProps<PracticeMarkPaidCard>) {
  return (
    <PracticeActionCardShell
      title="Mark an invoice paid"
      caseId={card.case_id}
      caseTitle={card.case_title}
      blockers={card.blockers}
      actionLabel="Mark paid"
      question={`Mark ${card.invoice_number ?? "this fee"} (${formatINR(card.amount)}) as paid today?`}
      onDismiss={onDismiss}
      run={async () => {
        await actions.markPaid(card.case_id, card.fee_id);
        return { text: "Marked paid. Any payment reminder still waiting for this invoice was dropped." };
      }}
    >
      {() => (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-gray-500">Invoice</dt>
          <dd className="text-gray-900">{card.invoice_number ?? "Not generated"}</dd>
          <dt className="text-gray-500">Amount</dt>
          <dd className="text-gray-900">{formatINR(card.amount)}</dd>
        </dl>
      )}
    </PracticeActionCardShell>
  );
}

/** Runs one call per ticked row, in order. A row that fails is reported and
 * the rest still run; the card then ends, so a retry can never repeat the
 * rows that already went through. */
async function runRows<T>(rows: T[], label: (row: T) => string, call: (row: T) => Promise<unknown>) {
  const failed: string[] = [];
  for (const row of rows) {
    try {
      await call(row);
    } catch (caught) {
      failed.push(`${label(row)}: ${apiErrorDetail(caught, "failed")}`);
    }
  }
  if (failed.length === rows.length) throw new Error(failed[0]);
  return failed;
}

export function BulkCreateFeesCard({ card, actions, onDismiss }: CardProps<PracticeBulkCreateFeesCard>) {
  const id = useId();
  const [ticked, setTicked] = useState<Set<number>>(() => new Set(card.rows.map((row) => row.hearing_id)));
  const [amounts, setAmounts] = useState<Record<number, string>>(() =>
    Object.fromEntries(card.rows.map((row) => [row.hearing_id, card.amount ?? ""])),
  );
  const chosen = card.rows.filter((row) => ticked.has(row.hearing_id));
  // An empty amount uses the profile's default appearance fee.
  const amountsOk = chosen.every((row) => amounts[row.hearing_id].trim() === "" || validAmount(amounts[row.hearing_id]));

  return (
    <PracticeActionCardShell
      title="Add fees for several hearings"
      blockers={card.blockers}
      actionLabel={`Add ${plural(chosen.length, "fee")}`}
      question={`Add ${plural(chosen.length, "pending appearance fee")}? No invoice is generated or sent.`}
      ready={chosen.length > 0 && amountsOk}
      onDismiss={onDismiss}
      run={async () => {
        const failed = await runRows(
          chosen,
          (row) => `${row.case_title} (${row.label})`,
          (row) =>
            actions.createFee(row.case_id, {
              hearing: row.hearing_id,
              category: card.category,
              ...(amounts[row.hearing_id].trim() ? { amount: amounts[row.hearing_id].trim() } : {}),
            }),
        );
        const added = chosen.length - failed.length;
        return {
          text: failed.length
            ? `Added ${plural(added, "fee")}. Not added: ${failed.join("; ")}.`
            : `Added ${plural(added, "fee")}. Each is pending until you generate its invoice.`,
        };
      }}
    >
      {(editable) => (
        <ul className="space-y-2">
          {card.rows.map((row) => (
            <li key={row.hearing_id} className="grid grid-cols-[auto_1fr_7rem] items-center gap-2">
              <input
                id={`${id}-tick-${row.hearing_id}`}
                type="checkbox"
                className="h-4 w-4"
                checked={ticked.has(row.hearing_id)}
                disabled={!editable}
                onChange={(e) =>
                  setTicked((prev) => {
                    const next = new Set(prev);
                    if (e.target.checked) next.add(row.hearing_id);
                    else next.delete(row.hearing_id);
                    return next;
                  })
                }
              />
              <label htmlFor={`${id}-tick-${row.hearing_id}`} className="min-w-0 break-words text-sm text-gray-900">
                {row.case_title}
                <span className="block text-xs text-gray-500">{row.label}</span>
              </label>
              <Input
                aria-label={`Amount for ${row.case_title}, ${row.label}`}
                inputMode="decimal"
                placeholder="Default fee"
                value={amounts[row.hearing_id]}
                disabled={!editable || !ticked.has(row.hearing_id)}
                onChange={(e) => setAmounts((prev) => ({ ...prev, [row.hearing_id]: e.target.value }))}
              />
            </li>
          ))}
        </ul>
      )}
    </PracticeActionCardShell>
  );
}

export function BulkSendInvoicesCard({ card, actions, onDismiss }: CardProps<PracticeBulkSendInvoicesCard>) {
  const id = useId();
  const sendable = card.rows.filter((row) => row.blockers.length === 0);
  const [ticked, setTicked] = useState<Set<number>>(() => new Set(sendable.map((row) => row.fee_id)));
  const chosen = sendable.filter((row) => ticked.has(row.fee_id));

  return (
    <PracticeActionCardShell
      title="Send invoices"
      blockers={sendable.length ? card.blockers : [...card.blockers, "None of these invoices can be sent yet."]}
      actionLabel={`Send ${plural(chosen.length, "invoice")}`}
      question={`Email ${plural(chosen.length, "invoice")} to the clients' billing addresses now?`}
      ready={chosen.length > 0}
      onDismiss={onDismiss}
      run={async () => {
        const failed = await runRows(
          chosen,
          (row) => row.invoice_number ?? row.case_title,
          (row) => actions.sendInvoice(row.case_id, row.fee_id),
        );
        const sent = chosen.length - failed.length;
        return {
          text: failed.length
            ? `Sent ${plural(sent, "invoice")}. Not sent: ${failed.join("; ")}.`
            : `Sent ${plural(sent, "invoice")}.`,
        };
      }}
    >
      {(editable) => (
        <ul className="space-y-2">
          {card.rows.map((row) => {
            const blocked = row.blockers.length > 0;
            return (
              <li key={row.fee_id} className="grid grid-cols-[auto_1fr_auto] items-start gap-2">
                <input
                  id={`${id}-tick-${row.fee_id}`}
                  type="checkbox"
                  className="mt-0.5 h-4 w-4"
                  checked={!blocked && ticked.has(row.fee_id)}
                  disabled={!editable || blocked}
                  onChange={(e) =>
                    setTicked((prev) => {
                      const next = new Set(prev);
                      if (e.target.checked) next.add(row.fee_id);
                      else next.delete(row.fee_id);
                      return next;
                    })
                  }
                />
                <label htmlFor={`${id}-tick-${row.fee_id}`} className="min-w-0 break-words text-sm text-gray-900">
                  {row.invoice_number ?? "Invoice"}, {row.case_title}
                  <span className="block text-xs text-gray-500">
                    {blocked ? row.blockers.join(" ") : `To ${row.recipient_email}`}
                  </span>
                </label>
                <span className="text-sm text-gray-900">{formatINR(row.amount)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </PracticeActionCardShell>
  );
}
