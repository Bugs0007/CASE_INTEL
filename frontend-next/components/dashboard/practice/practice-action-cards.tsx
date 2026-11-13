"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { usePracticeCardActions, type PracticeCardActions } from "@/hooks/use-practice-card-actions";
import { formatINR } from "@/lib/utils";
import type {
  PracticeAnyActionCard,
  PracticeCreateFeeCard,
  PracticeDeleteFeeCard,
  PracticeFeeCategory,
  PracticeFeeFields,
  PracticeGenerateInvoiceCard,
  PracticeStartDraftCard,
  PracticeUpdateFeeCard,
} from "@/types/practice";
import { PracticeActionCardShell } from "./practice-action-card-shell";
import { BulkCreateFeesCard, BulkSendInvoicesCard, CreateTaskCard, MarkPaidCard } from "./practice-more-cards";
import { caseHref } from "./routes";

const CATEGORIES: { value: PracticeFeeCategory; label: string }[] = [
  { value: "appearance", label: "Appearance" },
  { value: "hotel", label: "Hotel" },
  { value: "flight", label: "Flight" },
  { value: "other", label: "Other" },
];

const categoryLabel = (value: string) => CATEGORIES.find((c) => c.value === value)?.label ?? value;
const validAmount = (value: string) => value.trim() !== "" && Number.isFinite(Number(value)) && Number(value) > 0;

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="text-xs font-medium text-gray-600">
        {label}
      </label>
      {children}
    </div>
  );
}

function CategorySelect({
  id,
  value,
  disabled,
  onChange,
}: {
  id: string;
  value: PracticeFeeCategory;
  disabled: boolean;
  onChange: (value: PracticeFeeCategory) => void;
}) {
  return (
    <Select id={id} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value as PracticeFeeCategory)}>
      {CATEGORIES.map((c) => (
        <option key={c.value} value={c.value}>
          {c.label}
        </option>
      ))}
    </Select>
  );
}

interface CardProps<T> {
  card: T;
  actions: PracticeCardActions;
  onDismiss?: () => void;
}

export function CreateFeeCard({ card, actions, onDismiss }: CardProps<PracticeCreateFeeCard>) {
  const id = useId();
  const [hearing, setHearing] = useState(card.hearing_id === null ? "" : String(card.hearing_id));
  const [category, setCategory] = useState<PracticeFeeCategory>(card.category);
  const [amount, setAmount] = useState(card.amount ?? "");
  const [description, setDescription] = useState(card.description);

  const noHearings = card.hearing_options.length === 0;
  // Only an appearance fee may leave the amount empty (the default fee applies).
  const amountOk = amount.trim() === "" ? category === "appearance" : validAmount(amount);
  const blockers = noHearings ? [...card.blockers, "This case has no hearing to bill against."] : card.blockers;

  return (
    <PracticeActionCardShell
      title="Add a fee"
      caseId={card.case_id}
      caseTitle={card.case_title}
      blockers={blockers}
      actionLabel="Add fee"
      question="Add this fee to the hearing?"
      ready={hearing !== "" && amountOk}
      onDismiss={onDismiss}
      run={async () => {
        await actions.createFee(card.case_id, {
          hearing: Number(hearing),
          category,
          ...(amount.trim() !== "" ? { amount: amount.trim() } : {}),
          ...(description.trim() !== "" ? { notes: description.trim() } : {}),
        });
        return { text: "Fee added. It is pending until you generate its invoice." };
      }}
    >
      {(editable) => (
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Hearing" htmlFor={`${id}-hearing`}>
            <Select
              id={`${id}-hearing`}
              value={hearing}
              disabled={!editable}
              onChange={(event) => setHearing(event.target.value)}
            >
              <option value="">Choose a hearing</option>
              {card.hearing_options.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Category" htmlFor={`${id}-category`}>
            <CategorySelect id={`${id}-category`} value={category} disabled={!editable} onChange={setCategory} />
          </Field>
          <Field label="Amount" htmlFor={`${id}-amount`}>
            <Input
              id={`${id}-amount`}
              inputMode="decimal"
              value={amount}
              disabled={!editable}
              placeholder={category === "appearance" ? "Use your default fee" : "Amount in rupees"}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>
          <Field label="Description" htmlFor={`${id}-description`}>
            <Input
              id={`${id}-description`}
              value={description}
              disabled={!editable}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
        </div>
      )}
    </PracticeActionCardShell>
  );
}

export function UpdateFeeCard({ card, actions, onDismiss }: CardProps<PracticeUpdateFeeCard>) {
  const id = useId();
  const [amount, setAmount] = useState(card.proposed.amount ?? card.current.amount);
  const [category, setCategory] = useState<PracticeFeeCategory>(card.proposed.category ?? card.current.category);
  const [description, setDescription] = useState(card.proposed.description ?? card.current.description);

  // Only what differs from the fee as it stands is sent.
  const changes: PracticeFeeFields = {
    ...(amount.trim() !== card.current.amount ? { amount: amount.trim() } : {}),
    ...(category !== card.current.category ? { category } : {}),
    ...(description !== card.current.description ? { description } : {}),
  };
  const hasChange = Object.keys(changes).length > 0;

  return (
    <PracticeActionCardShell
      title="Change a fee"
      caseId={card.case_id}
      caseTitle={card.case_title}
      blockers={card.blockers}
      actionLabel="Change fee"
      question={card.invoice_number ? `Change the fee on invoice ${card.invoice_number}?` : "Change this fee?"}
      ready={hasChange && validAmount(amount)}
      onDismiss={onDismiss}
      run={async () => {
        await actions.updateFee(card.case_id, card.fee_id, changes);
        return { text: card.regenerates_invoice ? "Fee changed and the invoice PDF updated." : "Fee changed." };
      }}
    >
      {(editable) => (
        <>
          <dl className="grid grid-cols-[auto_1fr_1fr] gap-x-3 gap-y-1 text-sm">
            <dt className="text-gray-500">Invoice</dt>
            <dd className="col-span-2 text-gray-900">{card.invoice_number ?? "Not generated yet"}</dd>
            {hasChange && (
              <>
                <dt />
                <dd className="text-xs font-semibold text-gray-500">Now</dd>
                <dd className="text-xs font-semibold text-gray-500">Change to</dd>
              </>
            )}
            {changes.amount !== undefined && (
              <>
                <dt className="text-gray-500">Amount</dt>
                <dd className="text-gray-900">{formatINR(card.current.amount)}</dd>
                <dd className="text-gray-900">{validAmount(amount) ? formatINR(amount) : amount}</dd>
              </>
            )}
            {changes.category !== undefined && (
              <>
                <dt className="text-gray-500">Category</dt>
                <dd className="text-gray-900">{categoryLabel(card.current.category)}</dd>
                <dd className="text-gray-900">{categoryLabel(category)}</dd>
              </>
            )}
            {changes.description !== undefined && (
              <>
                <dt className="text-gray-500">Description</dt>
                <dd className="break-words text-gray-900">{card.current.description || "None"}</dd>
                <dd className="break-words text-gray-900">{description || "None"}</dd>
              </>
            )}
          </dl>
          {card.regenerates_invoice && (
            <p className="text-sm text-gray-700">The invoice PDF will be updated, same number.</p>
          )}
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="New amount" htmlFor={`${id}-amount`}>
              <Input
                id={`${id}-amount`}
                inputMode="decimal"
                value={amount}
                disabled={!editable}
                onChange={(event) => setAmount(event.target.value)}
              />
            </Field>
            <Field label="New category" htmlFor={`${id}-category`}>
              <CategorySelect id={`${id}-category`} value={category} disabled={!editable} onChange={setCategory} />
            </Field>
            <div className="sm:col-span-2">
              <Field label="New description" htmlFor={`${id}-description`}>
                <Input
                  id={`${id}-description`}
                  value={description}
                  disabled={!editable}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </Field>
            </div>
          </div>
        </>
      )}
    </PracticeActionCardShell>
  );
}

function FeeSummary({ category, amount, status }: { category: string; amount: string; status?: string }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
      <dt className="text-gray-500">Fee</dt>
      <dd className="text-gray-900">{categoryLabel(category)}</dd>
      <dt className="text-gray-500">Amount</dt>
      <dd className="text-gray-900">{formatINR(amount)}</dd>
      {status && (
        <>
          <dt className="text-gray-500">Status</dt>
          <dd className="text-gray-900">{status}</dd>
        </>
      )}
    </dl>
  );
}

export function GenerateInvoiceCard({ card, actions, onDismiss }: CardProps<PracticeGenerateInvoiceCard>) {
  return (
    <PracticeActionCardShell
      title="Generate an invoice"
      caseId={card.case_id}
      caseTitle={card.case_title}
      blockers={card.blockers}
      actionLabel="Generate invoice"
      question={`Generate the invoice for ${formatINR(card.amount)}? It will not be sent.`}
      onDismiss={onDismiss}
      run={async () => {
        await actions.generateInvoice(card.case_id, card.fee_id);
        return { text: "Invoice generated. It has not been sent." };
      }}
    >
      {() => <FeeSummary category={card.category} amount={card.amount} />}
    </PracticeActionCardShell>
  );
}

export function DeleteFeeCard({ card, actions, onDismiss }: CardProps<PracticeDeleteFeeCard>) {
  return (
    <PracticeActionCardShell
      title="Delete a pending fee"
      caseId={card.case_id}
      caseTitle={card.case_title}
      blockers={card.blockers}
      actionLabel="Delete fee"
      question={`Delete the fee of ${formatINR(card.amount)}? This cannot be undone.`}
      destructive
      onDismiss={onDismiss}
      run={async () => {
        await actions.deleteFee(card.case_id, card.fee_id);
        return { text: "Fee deleted." };
      }}
    >
      {() => <FeeSummary category={card.category} amount={card.amount} status={card.fee_status} />}
    </PracticeActionCardShell>
  );
}

export function StartDraftCard({ card, actions, onDismiss }: CardProps<PracticeStartDraftCard>) {
  const id = useId();
  const [instructions, setInstructions] = useState(card.instructions);
  // One request id per card, so a retry after a dropped reply cannot start two drafts.
  const requestId = useRef("");

  return (
    <PracticeActionCardShell
      title={`Start a draft: ${card.subtype_label}`}
      caseId={card.case_id}
      caseTitle={card.case_title}
      blockers={card.blockers}
      actionLabel="Start draft"
      question={`Start this ${card.subtype_label.toLowerCase()} for the case?`}
      onDismiss={onDismiss}
      run={async () => {
        if (!requestId.current) requestId.current = crypto.randomUUID();
        const draftId = await actions.createDraft({
          caseId: card.case_id,
          subtype: card.subtype,
          instructions: instructions.trim(),
          clientRequestId: requestId.current,
        });
        return {
          text: "Draft started. It will be ready to review shortly.",
          link: { href: `${caseHref(card.case_id)}?draft=${draftId}`, label: "Open draft" },
        };
      }}
    >
      {(editable) => (
        <Field label="Instructions" htmlFor={`${id}-instructions`}>
          <Textarea
            id={`${id}-instructions`}
            rows={3}
            maxLength={2000}
            value={instructions}
            disabled={!editable}
            onChange={(event) => setInstructions(event.target.value)}
          />
        </Field>
      )}
    </PracticeActionCardShell>
  );
}

/** Renders a turn's card when it is one of the new kinds. The send-invoice
 * card has its own component. */
export function PracticeActionCards({
  card,
  onDismiss,
}: {
  card: Exclude<PracticeAnyActionCard, { kind: "send_invoice" }>;
  onDismiss: () => void;
}) {
  const actions = usePracticeCardActions();
  switch (card.kind) {
    case "create_fee":
      return <CreateFeeCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "update_fee":
      return <UpdateFeeCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "generate_invoice":
      return <GenerateInvoiceCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "delete_fee":
      return <DeleteFeeCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "start_draft":
      return <StartDraftCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "create_task":
      return <CreateTaskCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "mark_invoice_paid":
      return <MarkPaidCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "bulk_create_fees":
      return <BulkCreateFeesCard card={card} actions={actions} onDismiss={onDismiss} />;
    case "bulk_send_invoices":
      return <BulkSendInvoicesCard card={card} actions={actions} onDismiss={onDismiss} />;
  }
}
