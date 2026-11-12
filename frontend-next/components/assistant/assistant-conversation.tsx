"use client";

import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { ChatPanel } from "@/components/chat/chat-panel";
import { PracticeChat } from "@/components/assistant/practice-chat";
import { ScopeChoices } from "@/components/assistant/scope-choices";
import { chatKeys } from "@/hooks/use-chat";
import { cn } from "@/lib/utils";
import type { AssistantScope } from "@/providers/assistant-provider";
import type { Citation } from "@/types";

/** The open chat for a scope, shared by the popover and the full page.
 * A case chat is the existing case chat (without its own History rail, the
 * caller owns the list); a practice chat is the practice assistant. */
export function AssistantConversation({
  scope,
  conversationId,
  onConversationChange,
  onChangeScope,
  compact = false,
  className,
}: {
  scope: AssistantScope | null;
  /** null is a new chat in this scope. */
  conversationId: number | null;
  onConversationChange: (id: number | null) => void;
  onChangeScope: (scope: AssistantScope | null) => void;
  compact?: boolean;
  className?: string;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();

  function changed(id: number | null) {
    // A new chat or a new answer moves the chat lists.
    queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    onConversationChange(id);
  }

  if (scope === null) {
    return (
      <div className={cn("space-y-2 overflow-y-auto p-3", className)}>
        <p className="text-sm text-gray-700">Pick what you want to ask about.</p>
        <ScopeChoices onPick={onChangeScope} />
      </div>
    );
  }

  if (scope.kind === "case") {
    return (
      <ChatPanel
        caseId={scope.caseId}
        compact={compact}
        hideHistory
        conversationId={conversationId}
        onConversationChange={changed}
        onOpenCitation={(citation: Citation) => {
          if (citation.document_id !== null) router.push(`/cases/${scope.caseId}?doc=${citation.document_id}`);
        }}
        className={cn("border-0 shadow-none", className)}
      />
    );
  }

  return (
    <div className={cn("min-h-0", className)}>
      <PracticeChat
        conversationId={conversationId}
        onConversationChange={changed}
        onUseCase={() => onChangeScope(null)}
      />
    </div>
  );
}
