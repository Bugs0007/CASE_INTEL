"use client";

import { useId, useState } from "react";
import Link from "next/link";
import { ArrowUpRight, ChevronDown, ChevronRight, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScopeChoices } from "@/components/assistant/scope-choices";
import { chatCaseLabel, chatTime, chatTitle, groupConversations, recentChats } from "@/lib/assistant";
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
  /** Case id to case number, so the filter can match a number. */
  caseNumbers?: Record<number, string | null | undefined>;
}

/** Practice chats shown before "Show all". */
const PRACTICE_VISIBLE = 5;

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

/** A row in "Recent": title, when, and which case (or Practice) it is about. */
function RecentRow({ chat, active, onSelect }: { chat: Conversation; active: boolean; onSelect: () => void }) {
  const label = chatCaseLabel(chat);
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={active ? "true" : undefined}
      className={cn(
        "flex min-h-[44px] w-full min-w-0 flex-col items-start rounded-lg px-2 py-1.5 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
        active ? "bg-gray-200" : "hover:bg-gray-100",
      )}
    >
      <span className="w-full truncate text-sm font-medium text-gray-900">{chatTitle(chat)}</span>
      <span className="flex w-full min-w-0 items-center gap-1.5 text-xs text-gray-500">
        <span className="ci-chip ci-chip--none max-w-[55%] truncate" title={label}>
          {label}
        </span>
        <span className="flex-shrink-0">{formatRelativeTime(chatTime(chat))}</span>
      </span>
    </button>
  );
}

function GroupHeading({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 px-2 pb-1 pt-3">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{children}</h3>
      {action}
    </div>
  );
}

/** The full page's chat list: a New chat button that asks for a scope, a
 * filter, then the eight newest chats, the practice chats, one collapsed
 * group per case, and older document chats. */
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
  caseNumbers,
}: SidebarProps) {
  const [filter, setFilter] = useState("");
  const [choosing, setChoosing] = useState(false);
  /** A group the advocate opened or closed by hand; absent means the default. */
  const [manual, setManual] = useState<Record<number, boolean>>({});
  const [showAllPractice, setShowAllPractice] = useState(false);
  const filterId = useId();
  const filtering = filter.trim() !== "";
  const groups = groupConversations(conversations, filter, caseNumbers);
  const recent = filtering ? [] : recentChats(conversations);
  const activeCaseId = conversations.find((chat) => chat.id === activeId)?.case_id ?? null;
  // Closed unless it holds the open chat or the filter matched it.
  const isOpen = (caseId: number) => manual[caseId] ?? (filtering || caseId === activeCaseId);
  const practiceVisible =
    filtering || showAllPractice || groups.practice.length <= PRACTICE_VISIBLE
      ? groups.practice
      : groups.practice.filter((chat, index) => index < PRACTICE_VISIBLE || chat.id === activeId);
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
            {recent.length > 0 && (
              <section aria-label="Recent">
                <GroupHeading>Recent</GroupHeading>
                <ul className="space-y-0.5">
                  {recent.map((chat) => (
                    <li key={chat.id}>
                      <RecentRow chat={chat} active={chat.id === activeId} onSelect={() => onSelect(chat.id)} />
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {PORTFOLIO_BOT_ENABLED && groups.practice.length > 0 && (
              <section aria-label="Your practice">
                <GroupHeading>Your practice</GroupHeading>
                <ul className="space-y-0.5">{practiceVisible.map(row)}</ul>
                {!filtering && groups.practice.length > PRACTICE_VISIBLE && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="mt-1 w-full"
                    onClick={() => setShowAllPractice((value) => !value)}
                  >
                    {showAllPractice ? "Show fewer" : `Show all (${groups.practice.length})`}
                  </Button>
                )}
              </section>
            )}
            {groups.cases.length > 0 && (
              <section aria-label="Cases">
                <GroupHeading
                  action={
                    groups.cases.some((group) => isOpen(group.caseId)) ? (
                      <button
                        type="button"
                        onClick={() => setManual(Object.fromEntries(groups.cases.map((group) => [group.caseId, false])))}
                        className="rounded px-1 text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      >
                        Collapse all
                      </button>
                    ) : null
                  }
                >
                  Cases
                </GroupHeading>
                <ul className="space-y-1">
                  {groups.cases.map((group) => {
                    const open = isOpen(group.caseId);
                    const count = `${group.chats.length} ${group.chats.length === 1 ? "chat" : "chats"}`;
                    return (
                      <li key={group.caseId} aria-label={group.title}>
                        <div className="flex items-center">
                          <button
                            type="button"
                            aria-expanded={open}
                            title={group.caseNumber ? `${group.title} (${group.caseNumber})` : group.title}
                            onClick={() => setManual((current) => ({ ...current, [group.caseId]: !open }))}
                            className="flex min-h-[44px] min-w-0 flex-1 items-center gap-1 rounded-lg text-left hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:min-h-9"
                          >
                            {open ? (
                              <ChevronDown className="h-4 w-4 flex-shrink-0 text-gray-500" aria-hidden="true" />
                            ) : (
                              <ChevronRight className="h-4 w-4 flex-shrink-0 text-gray-500" aria-hidden="true" />
                            )}
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-semibold text-gray-900">{group.title}</span>
                              <span className="block truncate text-xs text-gray-500">
                                {count} · {formatRelativeTime(chatTime(group.chats[0]))}
                              </span>
                            </span>
                          </button>
                          <Link
                            href={`/cases/${group.caseId}`}
                            aria-label={`Open case ${group.title}`}
                            className="flex h-11 w-9 flex-shrink-0 items-center justify-center rounded-lg text-gray-500 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-9"
                          >
                            <ArrowUpRight className="h-4 w-4" />
                          </Link>
                        </div>
                        {open && <ul className="ml-4 space-y-0.5">{group.chats.map(row)}</ul>}
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
