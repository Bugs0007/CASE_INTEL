"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronUp, Loader2, Send, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import {
  useDiscardClientMessage,
  useSendClientMessage,
  useUpdateClientMessage,
} from "@/hooks/use-clients";
import { apiErrorDetail } from "@/lib/api/client";
import { cn, formatDate, formatHearingDate } from "@/lib/utils";
import type { ClientMessage } from "@/types";

interface ClientMessageCardProps {
  message: ClientMessage;
  /** Show which case it belongs to (the inbox does; the case page doesn't). */
  showCase?: boolean;
  defaultOpen?: boolean;
}

function kindNoun(message: ClientMessage): string {
  return message.kind === "payment_reminder" ? "Reminder" : "Update";
}

/** One client email, from draft to sent.
 *
 * A draft is written by the system and goes nowhere until the advocate
 * presses Send. The send result is branched on explicitly: "logged" (the
 * server has no email credentials) gets its own warning toast and must
 * never read as delivered. */
export function ClientMessageCard({ message, showCase = false, defaultOpen = false }: ClientMessageCardProps) {
  const [open, setOpen] = useState(defaultOpen);
  const [subject, setSubject] = useState(message.subject);
  const [body, setBody] = useState(message.body);
  const [recipientIds, setRecipientIds] = useState<number[]>(message.recipients.map((r) => r.contact_id));

  const update = useUpdateClientMessage();
  const send = useSendClientMessage();
  const discard = useDiscardClientMessage();

  // Re-seed only when the server copy actually changes (updated_at moves:
  // a save, or the draft upgraded with the order summary) -- not on every
  // refetch, which would wipe edits the advocate is midway through.
  useEffect(() => {
    setSubject(message.subject);
    setBody(message.body);
    setRecipientIds(message.recipients.map((r) => r.contact_id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [message.updated_at]);

  const isDraft = message.status === "draft";
  const dirty =
    subject !== message.subject ||
    body !== message.body ||
    recipientIds.join(",") !== message.recipients.map((r) => r.contact_id).join(",");
  const busy = update.isPending || send.isPending || discard.isPending;

  async function save(): Promise<boolean> {
    try {
      await update.mutateAsync({
        id: message.id,
        data: { subject, body, recipient_contact_ids: recipientIds },
      });
      return true;
    } catch (error) {
      showToast.error("Could not save the draft", apiErrorDetail(error, "Please try again."));
      return false;
    }
  }

  async function handleSend() {
    if (recipientIds.length === 0) {
      showToast.error("No recipients", "Choose at least one client contact to send this to.");
      return;
    }
    if (dirty && !(await save())) return;
    try {
      const result = await send.mutateAsync(message.id);
      if (result.sent) {
        showToast.success(`${kindNoun(message)} sent`, `Emailed to ${result.recipients.join(", ")}.`);
      } else {
        // sent=false is a 200, not an error: no mail credentials on the
        // server, so the message was only LOGGED. Saying "sent" would be
        // a lie the message's own status contradicts.
        showToast.warning(
          `${kindNoun(message)} logged, not emailed`,
          result.missing_env_vars?.length
            ? `${result.detail} Missing: ${result.missing_env_vars.join(", ")}.`
            : result.detail,
        );
      }
    } catch (error) {
      showToast.error(`Could not send the ${kindNoun(message).toLowerCase()}`, apiErrorDetail(error, "Please try again."));
    }
  }

  async function handleDiscard() {
    if (!confirm("Discard this draft? It won't be suggested again.")) return;
    try {
      await discard.mutateAsync(message.id);
      showToast.info("Draft discarded");
    } catch (error) {
      showToast.error("Could not discard", apiErrorDetail(error, "Please try again."));
    }
  }

  function toggleRecipient(id: number) {
    setRecipientIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  const statusChip =
    message.status === "sent" ? "ci-chip--ok" : message.status === "logged" ? "ci-chip--pending" : "ci-chip--none";

  return (
    <div className="rounded-lg border border-gray-100">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-start gap-3 px-3 py-2.5 text-left hover:bg-gray-50 rounded-lg"
      >
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="ci-chip ci-chip--none">{message.kind_display}</span>
            <span className={cn("ci-chip", statusChip)}>
              {message.status === "logged" ? "Logged, not emailed" : message.status_display}
            </span>
            {message.edited_by_user && isDraft && <span className="text-xs text-gray-500">edited</span>}
          </div>
          <div className="mt-1 text-sm font-medium text-gray-900 truncate">{message.subject}</div>
          <div className="text-xs text-gray-500">
            {showCase && (
              <>
                {/* Imported titles usually already start with the number. */}
                {message.case_title.includes(message.case_number)
                  ? message.case_title
                  : `${message.case_number} · ${message.case_title}`}{" "}
                ·{" "}
              </>
            )}
            {message.hearing_date ? `Hearing ${formatHearingDate(message.hearing_date)} · ` : ""}
            {message.sent_at ? `Sent ${formatDate(message.sent_at)}` : `Drafted ${formatDate(message.created_at)}`}
          </div>
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-gray-400 mt-1" /> : <ChevronDown className="h-4 w-4 text-gray-400 mt-1" />}
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-3 border-t border-gray-100 pt-3">
          {showCase && (
            <Link href={`/cases/${message.case}`} className="text-xs text-primary underline">
              Open case
            </Link>
          )}

          {isDraft ? (
            <>
              <div>
                <span className="block text-xs font-medium text-gray-700 mb-1">To</span>
                {message.eligible_recipients.length === 0 ? (
                  <p className="text-xs text-status-alert">
                    No client contact on this case can receive this -- add an email address to a
                    contact (and check they haven&apos;t opted out) from Edit Case Details.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-3">
                    {message.eligible_recipients.map((r) => (
                      <label key={r.contact_id} className="flex items-center gap-1.5 text-sm text-gray-700">
                        <input
                          type="checkbox"
                          checked={recipientIds.includes(r.contact_id)}
                          onChange={() => toggleRecipient(r.contact_id)}
                        />
                        {r.name} <span className="text-gray-400">&lt;{r.email}&gt;</span>
                      </label>
                    ))}
                  </div>
                )}
              </div>
              <div>
                <label htmlFor={`subject-${message.id}`} className="block text-xs font-medium text-gray-700 mb-1">
                  Subject
                </label>
                <Input id={`subject-${message.id}`} value={subject} onChange={(e) => setSubject(e.target.value)} />
              </div>
              <div>
                <label htmlFor={`body-${message.id}`} className="block text-xs font-medium text-gray-700 mb-1">
                  Message
                </label>
                <Textarea
                  id={`body-${message.id}`}
                  value={body}
                  rows={10}
                  onChange={(e) => setBody(e.target.value)}
                  className="font-sans"
                />
              </div>
              <div className="flex flex-wrap justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={handleDiscard} disabled={busy}>
                  <Trash2 className="h-4 w-4" />
                  Discard
                </Button>
                {dirty && (
                  <Button variant="secondary" size="sm" onClick={save} disabled={busy}>
                    Save draft
                  </Button>
                )}
                <Button size="sm" onClick={handleSend} disabled={busy}>
                  {send.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Send
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="text-xs text-gray-600">
                To: {message.recipients.map((r) => `${r.name} <${r.email}>`).join(", ") || "—"}
              </div>
              {message.discard_reason && (
                <div className="text-xs text-gray-500">{message.discard_reason}</div>
              )}
              <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800">{message.body}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}
