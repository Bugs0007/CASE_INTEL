"use client";

import Link from "next/link";
import { useId, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { PracticeCaseCandidate, PracticeTurn } from "@/types/practice";
import { formatAsOf } from "./format";
import { PracticeActionCards } from "./practice-action-cards";
import { PracticeInvoiceActionCard } from "./practice-invoice-action-card";
import { PracticeReportCard } from "./practice-report-card";
import { referenceHref } from "./routes";

/** The closed set of questions the assistant answers from the chips. */
export const SUGGESTED_QUESTIONS = [
  { intent: "overview", label: "Practice overview", query: "Give me an overview of my practice." },
  { intent: "calendar", label: "This week's calendar", query: "What is on my calendar this week?" },
  { intent: "open_deadlines", label: "Open deadlines", query: "What deadlines are open?" },
  { intent: "missing_next_date", label: "Cases with no next date", query: "Which cases have no next date?" },
] as const;

export type PracticeMessage =
  | { role: "user"; id: string; text: string }
  | { role: "assistant"; id: string; turn: PracticeTurn }
  /** A line from this page, not the assistant: the result of confirming an action. */
  | { role: "notice"; id: string; text: string; tone: "info" | "warning" | "error" };

interface MessageHandlers {
  onChooseCase: (caseId: number) => void;
  onConfirmInvoice: (feeId: number) => void;
  onDismissAction: (messageId: string) => void;
  /** Opens a new chat for this case with the question typed but not sent. */
  onAskInCase?: (candidate: PracticeCaseCandidate) => void;
  /** The fee whose send is in flight, if any. */
  confirmingFeeId?: number | null;
}

function AssistantTurn({ id, turn, handlers }: { id: string; turn: PracticeTurn; handlers: MessageHandlers }) {
  const asOf = formatAsOf(turn.as_of);
  const caseTitle = turn.action_card
    ? turn.sources.find((ref) => ref.kind === "case" && (ref.case_id ?? ref.id) === turn.action_card!.case_id)?.label
    : null;
  return (
    <div className="max-w-full space-y-2 rounded-lg bg-gray-50 p-3">
      <p className="whitespace-pre-wrap break-words text-sm text-gray-900">{turn.answer}</p>

      {turn.status === "partial" && (
        <p className="rounded bg-amber-50 p-2 text-xs text-amber-900">
          Part of this answer could not be checked, so it may be incomplete.
        </p>
      )}
      {turn.status === "needs_clarification" && (
        <p className="rounded bg-blue-50 p-2 text-xs text-blue-900">I need a little more detail to answer this.</p>
      )}

      {turn.case_candidates.length > 0 && (
        <div role="group" aria-label="Choose a case" className="space-y-1">
          <p className="text-xs font-semibold text-gray-600">Which case do you mean?</p>
          <ul className="space-y-1">
            {turn.case_candidates.map((candidate) => (
              <li key={candidate.id} className="flex items-stretch gap-1">
                <button
                  type="button"
                  onClick={() => handlers.onChooseCase(candidate.id)}
                  className="flex min-h-[44px] min-w-0 flex-1 flex-col items-start rounded-lg border border-gray-200 bg-surface px-3 py-2 text-left hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <span className="break-words text-sm font-medium text-gray-900">{candidate.title}</span>
                  <span className="break-words text-xs text-gray-500">
                    {[candidate.case_number, candidate.court].filter(Boolean).join(" · ")}
                  </span>
                </button>
                {handlers.onAskInCase && (
                  <button
                    type="button"
                    aria-label={`Ask in this case: ${candidate.title}`}
                    onClick={() => handlers.onAskInCase?.(candidate)}
                    className="min-h-[44px] flex-shrink-0 rounded-lg border border-gray-200 bg-surface px-2.5 text-xs font-semibold text-primary hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    Ask in this case
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {turn.action_card?.kind === "send_invoice" && (
        <PracticeInvoiceActionCard
          card={turn.action_card}
          caseTitle={caseTitle}
          confirming={handlers.confirmingFeeId === turn.action_card.fee_id}
          onConfirm={handlers.onConfirmInvoice}
          onDismiss={() => handlers.onDismissAction(id)}
        />
      )}
      {turn.action_card && turn.action_card.kind !== "send_invoice" && (
        <PracticeActionCards card={turn.action_card} onDismiss={() => handlers.onDismissAction(id)} />
      )}
      {turn.report && <PracticeReportCard card={turn.report} />}

      {turn.sources.length > 0 && (
        <ul aria-label="Sources" className="flex flex-wrap gap-1.5">
          {turn.sources.map((ref) => (
            <li key={`${ref.kind}-${ref.id}`} className="min-w-0">
              <Link
                href={referenceHref(ref)}
                className="ci-chip ci-chip--none max-w-full break-words hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                {ref.label}
              </Link>
            </li>
          ))}
        </ul>
      )}

      {asOf && <p className="text-xs text-gray-500">As of {asOf}</p>}
    </div>
  );
}

export interface PracticeMessageListProps extends MessageHandlers {
  messages: PracticeMessage[];
}

/** The conversation, announced politely as new answers arrive. */
export function PracticeMessageList({ messages, ...handlers }: PracticeMessageListProps) {
  return (
    <div role="log" aria-live="polite" aria-label="Conversation" className="space-y-3">
      {messages.map((message) =>
        message.role === "user" ? (
          <div key={message.id} className="flex justify-end">
            <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-lg bg-primary px-3 py-2 text-sm text-page">
              {message.text}
            </p>
          </div>
        ) : message.role === "notice" ? (
          <p
            key={message.id}
            role={message.tone === "error" ? "alert" : "status"}
            className={cn(
              "rounded-lg p-2 text-sm",
              message.tone === "info" && "bg-green-50 text-green-900",
              message.tone === "warning" && "bg-amber-50 text-amber-900",
              message.tone === "error" && "bg-red-50 text-red-800",
            )}
          >
            {message.text}
          </p>
        ) : (
          <AssistantTurn key={message.id} id={message.id} turn={message.turn} handlers={handlers} />
        ),
      )}
    </div>
  );
}

export interface PracticeAssistantPanelProps extends MessageHandlers {
  messages: PracticeMessage[];
  /** Waiting for an answer. */
  pending: boolean;
  /** The last request failed. */
  error: boolean;
  onRetry: () => void;
  /** The input's text. Set it from outside to prefill without sending. */
  draft: string;
  onDraftChange: (draft: string) => void;
  onSend: (query: string) => void;
}

/** The assistant's body without its card: suggested questions, the
 * conversation, and the input. The dashboard wraps it in a card; the Case Bot
 * popover and page use it as it is. It sends only when the advocate presses
 * Send or picks a chip. */
export function PracticeAssistantBody({
  messages,
  pending,
  error,
  onRetry,
  draft,
  onDraftChange,
  onSend,
  stickyInput = false,
  ...handlers
}: PracticeAssistantPanelProps & {
  /** Keep the input at the bottom of a scrolling parent. */
  stickyInput?: boolean;
}) {
  const inputId = useId();

  function submit(event: FormEvent) {
    event.preventDefault();
    const query = draft.trim();
    if (!query || pending) return;
    onSend(query);
    onDraftChange("");
  }

  return (
    <div className="space-y-3">
      <ul aria-label="Suggested questions" className="flex flex-wrap gap-1.5">
        {SUGGESTED_QUESTIONS.map((item) => (
          <li key={item.intent}>
            <button
              type="button"
              disabled={pending}
              onClick={() => onSend(item.query)}
              className={cn(
                "min-h-[44px] rounded-full border border-gray-200 bg-surface px-3 text-xs font-medium text-gray-800 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-50 md:min-h-8",
              )}
            >
              {item.label}
            </button>
          </li>
        ))}
      </ul>

      {messages.length > 0 && <PracticeMessageList messages={messages} {...handlers} />}

      {pending && (
        <p role="status" className="text-sm text-gray-500">
          Looking through your records.
        </p>
      )}

      {error && !pending && (
        <div role="alert" className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
          <p className="text-sm text-red-800">That question could not be answered.</p>
          <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
      )}

      <form
        onSubmit={submit}
        className={cn("flex gap-2", stickyInput && "sticky bottom-0 -mx-3 border-t border-gray-100 bg-surface p-3")}
      >
        <label htmlFor={inputId} className="sr-only">
          Your question
        </label>
        <input
          id={inputId}
          type="text"
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder="Ask about your cases, hearings or deadlines"
          className="h-11 min-w-0 flex-1 rounded-lg border border-gray-200 bg-surface px-3 text-sm placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-10"
        />
        <Button type="submit" size="md" disabled={pending || draft.trim() === ""}>
          Send
        </Button>
      </form>
    </div>
  );
}

/** "Ask about your practice" on the dashboard: the body in a card. */
export function PracticeAssistantPanel(props: PracticeAssistantPanelProps) {
  return (
    <Card aria-labelledby="practice-assistant-title">
      <CardHeader>
        <CardTitle id="practice-assistant-title">Ask about your practice</CardTitle>
      </CardHeader>
      <CardContent className="px-3 sm:px-5">
        <PracticeAssistantBody {...props} />
      </CardContent>
    </Card>
  );
}
