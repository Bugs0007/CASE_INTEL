"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  PracticeAssistantBody,
  type PracticeMessage,
} from "@/components/dashboard/practice/practice-assistant-panel";
import { useConversationMessages } from "@/hooks/use-chat";
import { usePracticeConversation } from "@/hooks/use-practice-conversation";
import { rebuildPracticeMessages } from "@/lib/practice-history";
import type { AssistantAsk } from "@/providers/assistant-provider";
import type { PracticeCaseCandidate } from "@/types/practice";

/** The latest thing the advocate typed in this chat. */
function lastQuestion(messages: PracticeMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message.role === "user") return message.text;
  }
  return "";
}

function Session({
  initialMessages,
  conversationId,
  onConversation,
  onUseCase,
  ask,
  onAskConsumed,
  onAskInCase,
}: {
  initialMessages: PracticeMessage[];
  conversationId?: number;
  onConversation: (id: number) => void;
  onUseCase?: () => void;
  ask?: AssistantAsk | null;
  onAskConsumed?: (id: number) => void;
  onAskInCase?: (candidate: PracticeCaseCandidate, question: string) => void;
}) {
  const convo = usePracticeConversation({ initialMessages, conversationId, onConversation });

  // A question handed in from outside (the dashboard ask bar) is sent once,
  // as the first message of this new chat.
  const handledAsk = useRef<number | null>(null);
  useEffect(() => {
    if (!ask || !ask.send || ask.scope.kind !== "practice" || handledAsk.current === ask.id) return;
    handledAsk.current = ask.id;
    convo.send(ask.question, undefined, ask.selectedDay);
    onAskConsumed?.(ask.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ask]);
  // Keep the newest exchange in view: scroll down when a question goes out
  // and when its answer arrives.
  // Keep the newest exchange in view. The chat sticks to its end while the
  // advocate is at (or near) the bottom, including when an opened chat or a
  // card finishes laying out; scrolling up to read stops the following.
  const scroller = useRef<HTMLDivElement>(null);
  const atEnd = useRef(true);
  useEffect(() => {
    const box = scroller.current;
    if (!box) return;
    const toEnd = () => {
      if (atEnd.current) box.scrollTop = box.scrollHeight;
    };
    const onScroll = () => {
      atEnd.current = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    };
    box.addEventListener("scroll", onScroll, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(toEnd);
    if (box.firstElementChild) observer?.observe(box.firstElementChild);
    toEnd();
    return () => {
      box.removeEventListener("scroll", onScroll);
      observer?.disconnect();
    };
  }, []);
  // A question just sent always brings the end back into view.
  useEffect(() => {
    if (!convo.pending) return;
    atEnd.current = true;
    const box = scroller.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [convo.pending]);

  return (
    <div ref={scroller} className="h-full overflow-y-auto overscroll-contain px-3 pt-3">
      {convo.unavailable ? (
        <div role="alert" className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-sm text-amber-900">The practice assistant is not switched on yet.</p>
          {onUseCase && (
            <Button type="button" variant="secondary" size="sm" onClick={onUseCase}>
              Ask about a case instead
            </Button>
          )}
        </div>
      ) : (
        <PracticeAssistantBody
          messages={convo.messages}
          pending={convo.pending}
          error={convo.error}
          onRetry={convo.retry}
          draft={convo.draft}
          onDraftChange={convo.setDraft}
          onSend={convo.send}
          onChooseCase={convo.chooseCase}
          onConfirmInvoice={convo.confirm}
          onDismissAction={convo.dismissAction}
          confirmingFeeId={convo.confirmingFeeId}
          onAskInCase={onAskInCase ? (candidate) => onAskInCase(candidate, lastQuestion(convo.messages)) : undefined}
          stickyInput
        />
      )}
    </div>
  );
}

/** A practice chat: a new one (conversationId null) or a past one, rebuilt
 * from its stored messages. When the first answer of a new chat names the
 * conversation it is reported, and the session keeps going without reloading. */
export function PracticeChat({
  conversationId,
  onConversationChange,
  onUseCase,
  ask,
  onAskConsumed,
  onAskInCase,
}: {
  conversationId: number | null;
  onConversationChange: (id: number | null) => void;
  /** Offered when the server has the practice assistant switched off. */
  onUseCase?: () => void;
  /** A question waiting to be sent as this new chat's first message. */
  ask?: AssistantAsk | null;
  onAskConsumed?: (id: number) => void;
  /** "Ask in this case" on a case candidate. */
  onAskInCase?: (candidate: PracticeCaseCandidate, question: string) => void;
}) {
  // The id this session itself created: selecting it from outside is not a
  // new selection, so it must not remount the session.
  const ownId = useRef<number | null>(conversationId);
  const [session, setSession] = useState({ n: 0, id: conversationId });
  useEffect(() => {
    if (conversationId !== ownId.current) {
      ownId.current = conversationId;
      setSession((current) => ({ n: current.n + 1, id: conversationId }));
    }
  }, [conversationId]);

  const messages = useConversationMessages(session.id);
  if (session.id !== null && (messages.isLoading || messages.isFetching)) {
    return (
      <p role="status" className="p-4 text-sm text-gray-500">
        Loading this chat.
      </p>
    );
  }
  if (session.id !== null && messages.isError) {
    return (
      <div role="alert" className="m-3 space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
        <p className="text-sm text-red-800">This chat could not be loaded.</p>
        <Button type="button" variant="secondary" size="sm" onClick={() => messages.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  return (
    <Session
      key={session.n}
      initialMessages={session.id !== null && messages.data ? rebuildPracticeMessages(messages.data, session.id) : []}
      conversationId={session.id ?? undefined}
      onUseCase={onUseCase}
      ask={ask}
      onAskConsumed={onAskConsumed}
      onAskInCase={onAskInCase}
      onConversation={(id) => {
        ownId.current = id;
        onConversationChange(id);
      }}
    />
  );
}
