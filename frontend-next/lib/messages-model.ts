import type { ClientMessage, ClientMessageKind, SentMessage } from "@/types";

/** What the Messages page works out from the drafts and the sent log, as
 * plain functions so it can be tested. */

export type DraftFilter = ClientMessageKind | "all";
export type SentFilter = "all" | "sent" | "logged";

export const DRAFT_FILTERS: { value: DraftFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "case_update", label: "Case updates" },
  { value: "payment_reminder", label: "Payment reminders" },
];

export const SENT_FILTERS: { value: SentFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "sent", label: "Emailed" },
  { value: "logged", label: "Logged, not emailed" },
];

// "Dear Meera Nair," -- the salutation says nothing about what the email is.
const SALUTATION = /^(dear|hello|hi|respected)\b[^.!?:]{0,80}[,:]?$/i;

/** The first words of what a message actually says: the salutation line is
 * skipped, the rest is joined into one line and cut at `max` characters. */
export function messagePreview(body: string, max = 120): string {
  const lines = body
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const said = lines.filter((line) => !SALUTATION.test(line));
  const text = (said.length > 0 ? said : lines).join(" ").replace(/\s+/g, " ");
  return text.length > max ? `${text.slice(0, max - 1).trimEnd()}…` : text;
}

/** "Meera Nair, Rao Builders" -- who a draft is addressed to (the contacts
 * ticked), "" when nobody is. */
export function recipientNames(message: Pick<ClientMessage, "recipients">): string {
  return message.recipients.map((r) => r.name || r.email).join(", ");
}

/** Imported case titles often start with the number already. */
export function messageCaseLabel(message: Pick<ClientMessage, "case_number" | "case_title">): string {
  const { case_number: number, case_title: title } = message;
  if (!number) return title;
  if (!title || title.includes(number)) return title || number;
  return `${number} · ${title}`;
}

function matches(haystack: string[], query: string): boolean {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const text = haystack.join(" ").toLowerCase();
  return words.every((word) => text.includes(word));
}

export function draftCounts(drafts: ClientMessage[]): Record<DraftFilter, number> {
  return {
    all: drafts.length,
    case_update: drafts.filter((m) => m.kind === "case_update").length,
    payment_reminder: drafts.filter((m) => m.kind === "payment_reminder").length,
  };
}

export function filterDrafts(drafts: ClientMessage[], kind: DraftFilter, query: string): ClientMessage[] {
  return drafts.filter(
    (m) =>
      (kind === "all" || m.kind === kind) &&
      matches(
        [
          m.subject,
          m.case_number,
          m.case_title,
          m.kind_display,
          m.invoice_number ?? "",
          ...m.recipients.flatMap((r) => [r.name, r.email]),
        ],
        query,
      ),
  );
}

export function sentCounts(rows: SentMessage[]): Record<SentFilter, number> {
  return {
    all: rows.length,
    sent: rows.filter((r) => r.delivery === "sent").length,
    logged: rows.filter((r) => r.delivery !== "sent").length,
  };
}

export function filterSent(rows: SentMessage[], delivery: SentFilter, query: string): SentMessage[] {
  return rows.filter(
    (r) =>
      (delivery === "all" || (delivery === "sent" ? r.delivery === "sent" : r.delivery !== "sent")) &&
      matches([r.subject, r.case_number ?? "", r.case_title ?? "", r.kind_display, ...r.to_emails], query),
  );
}
