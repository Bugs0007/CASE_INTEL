"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScopeChoices } from "@/components/assistant/scope-choices";
import { chatTime, chatTitle, groupConversations } from "@/lib/assistant";
import { PORTFOLIO_BOT_ENABLED } from "@/lib/feature-flags";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { AssistantScope } from "@/providers/assistant-provider";
import type { Conversation } from "@/types/chat";

interface SidebarProps {
  conversations: Conversation[];
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  activeId: number | null;
  onSelect: (id: number) => void;
  onNewChat: (scope: AssistantScope) => void;
  onDelete: (id: number) => void;
  /** The chat whose delete is in flight. */
  deletingId: number | null;
  /** A delete failed. */
  deleteError: boolean;
}

function ChatRow({
  chat,
  active,
  deleting,
  onSelect,
  onDelete,
}: {
  chat: Conversation;
  active: boolean;
  deleting: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const title = chatTitle(chat);
  if (confirming) {
    return (
      <div role="group" aria-label={`Delete ${title}`} className="space-y-1.5 rounded-lg bg-red-50 p-2">
        <p className="break-words text-xs text-red-900">Delete this chat? This cannot be undone.</p>
        <div className="flex gap-2">
          <Button type="button" variant="danger" size="sm" disabled={deleting} onClick={onDelete}>
            Delete
          </Button>
          <Button type="button" variant="secondary" size="sm" disabled={deleting} onClick={() => setConfirming(false)}>
            Cancel
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className={cn("group flex items-center rounded-lg", active ? "bg-gray-200" : "hover:bg-gray-100")}>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "true" : undefined}
        className="flex min-h-[44px] min-w-0 flex-1 flex-col items-start rounded-lg px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="w-full truncate text-sm font-medium text-gray-900">{title}</span>
        <span className="text-xs text-gray-500">{formatRelativeTime(chatTime(chat))}</span>
      </button>
      <button
        type="button"
        aria-label={`Delete chat ${title}`}
        onClick={() => setConfirming(true)}
        className="mr-1 flex h-11 w-9 flex-shrink-0 items-center justify-center rounded-lg text-gray-500 hover:text-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-8"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}

function GroupHeading({ children }: { children: React.ReactNode }) {
  return <h3 className="px-2 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-gray-500">{children}</h3>;
}

/** The full page's chat list: a New chat button that asks for a scope, a
 * filter, then the practice chats, one group per case, and older document
 * chats. */
export function ConversationSidebar({
  conversations,
  loading,
  error,
  onRetry,
  activeId,
  onSelect,
  onNewChat,
  onDelete,
  deletingId,
  deleteError,
}: SidebarProps) {
  const [filter, setFilter] = useState("");
  const [choosing, setChoosing] = useState(false);
  const [collapsed, setCollapsed] = useState<Record<number, boolean>>({});
  const filterId = useId();
  const groups = groupConversations(conversations, filter);
  const empty = groups.practice.length + groups.cases.length + groups.legacy.length === 0;

  const row = (chat: Conversation) => (
    <li key={chat.id}>
      <ChatRow
        chat={chat}
        active={chat.id === activeId}
        deleting={deletingId === chat.id}
        onSelect={() => onSelect(chat.id)}
        onDelete={() => onDelete(chat.id)}
      />
    </li>
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-gray-100 p-3">
        <Button type="button" className="w-full" aria-expanded={choosing} onClick={() => setChoosing((value) => !value)}>
          <Plus className="h-4 w-4" />
          New chat
        </Button>
        {choosing && (
          <div className="rounded-lg border border-gray-200 bg-surface p-2">
            <p className="px-2 pb-1 text-xs font-semibold text-gray-600">What is the chat about?</p>
            <ScopeChoices
              onPick={(scope) => {
                setChoosing(false);
                onNewChat(scope);
              }}
            />
          </div>
        )}
        <label htmlFor={filterId} className="sr-only">
          Filter chats
        </label>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
          <input
            id={filterId}
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter chats and cases"
            className="h-11 w-full rounded-lg border border-gray-200 bg-surface pl-8 pr-3 text-sm placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-9"
          />
        </div>
      </div>

      <nav aria-label="Chats" className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-4">
        {deleteError && (
          <p role="alert" className="mt-2 rounded-lg bg-red-50 p-2 text-xs text-red-800">
            That chat could not be deleted. Try again.
          </p>
        )}
        {loading ? (
          <p role="status" className="px-2 py-4 text-sm text-gray-500">
            Loading your chats.
          </p>
        ) : error ? (
          <div role="alert" className="m-2 space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
            <p className="text-sm text-red-800">Your chats could not be loaded.</p>
            <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
              Try again
            </Button>
          </div>
        ) : empty ? (
          <p className="px-2 py-4 text-sm text-gray-500">
            {filter.trim() ? "No chat or case matches that filter." : "No chats yet. Start one with New chat."}
          </p>
        ) : (
          <>
            {PORTFOLIO_BOT_ENABLED && groups.practice.length > 0 && (
              <section aria-label="Your practice">
                <GroupHeading>Your practice</GroupHeading>
                <ul className="space-y-0.5">{groups.practice.map(row)}</ul>
              </section>
            )}
            {groups.cases.length > 0 && (
              <section aria-label="Cases">
                <GroupHeading>Cases</GroupHeading>
                <ul className="space-y-1">
                  {groups.cases.map((group) => {
                    const isCollapsed = collapsed[group.caseId] === true;
                    return (
                      <li key={group.caseId} aria-label={group.title}>
                        <div className="flex items-center">
                          <button
                            type="button"
                            aria-expanded={!isCollapsed}
                            aria-label={`${isCollapsed ? "Expand" : "Collapse"} ${group.title}`}
                            onClick={() => setCollapsed((current) => ({ ...current, [group.caseId]: !isCollapsed }))}
                            className="flex h-11 w-8 flex-shrink-0 items-center justify-center text-gray-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-8"
                          >
                            {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                          </button>
                          <Link
                            href={`/cases/${group.caseId}`}
                            className="min-w-0 flex-1 truncate rounded px-1 py-2 text-sm font-semibold text-gray-900 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                          >
                            {group.title}
                          </Link>
                        </div>
                        {!isCollapsed && <ul className="ml-4 space-y-0.5">{group.chats.map(row)}</ul>}
                      </li>
                    );
                  })}
                </ul>
              </section>
            )}
            {groups.legacy.length > 0 && (
              <section aria-label="Older document chats">
                <GroupHeading>Older document chats</GroupHeading>
                <ul className="space-y-0.5">{groups.legacy.map(row)}</ul>
              </section>
            )}
          </>
        )}
      </nav>
    </div>
  );
}
