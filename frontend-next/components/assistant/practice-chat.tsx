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

function Session({
  initialMessages,
  conversationId,
  onConversation,
  onUseCase,
}: {
  initialMessages: PracticeMessage[];
  conversationId?: number;
  onConversation: (id: number) => void;
  onUseCase?: () => void;
}) {
  const convo = usePracticeConversation({ initialMessages, conversationId, onConversation });
  return (
    <div className="h-full overflow-y-auto overscroll-contain px-3 pt-3">
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
}: {
  conversationId: number | null;
  onConversationChange: (id: number | null) => void;
  /** Offered when the server has the practice assistant switched off. */
  onUseCase?: () => void;
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
      onConversation={(id) => {
        ownId.current = id;
        onConversationChange(id);
      }}
    />
  );
}
