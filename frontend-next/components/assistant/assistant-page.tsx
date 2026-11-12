"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { MessagesSquare, PanelLeft } from "lucide-react";
import { AssistantConversation } from "@/components/assistant/assistant-conversation";
import { ConversationSidebar } from "@/components/assistant/conversation-sidebar";
import { ScopeChoices } from "@/components/assistant/scope-choices";
import { useScopeLabel } from "@/components/assistant/scope-picker";
import { Button } from "@/components/ui/button";
import { useConversationList, useConversationMessages, useDeleteConversation } from "@/hooks/use-chat";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { isPracticeUnavailable } from "@/hooks/use-practice-assistant";
import { assistantHref } from "@/lib/assistant";
import { PORTFOLIO_BOT_ENABLED } from "@/lib/feature-flags";
import { cn } from "@/lib/utils";
import type { AssistantScope } from "@/providers/assistant-provider";
import type { Conversation } from "@/types/chat";

/** A chat from before chats belonged to a case: read only. */
function LegacyTranscript({ id }: { id: number }) {
  const messages = useConversationMessages(id);
  if (messages.isLoading) {
    return (
      <p role="status" className="p-4 text-sm text-gray-500">
        Loading this chat.
      </p>
    );
  }
  if (messages.isError) {
    return (
      <div role="alert" className="m-4 space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
        <p className="text-sm text-red-800">This chat could not be loaded.</p>
        <Button type="button" variant="secondary" size="sm" onClick={() => messages.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  return (
    <div className="h-full space-y-3 overflow-y-auto p-4">
      <p className="text-xs text-gray-500">This is an older document chat. It can be read but not continued.</p>
      {(messages.data ?? []).map((message) => (
        <p
          key={message.id}
          className={cn(
            "max-w-[90%] whitespace-pre-wrap break-words rounded-lg p-3 text-sm",
            message.role === "user" ? "ml-auto bg-primary text-page" : "bg-gray-50 text-gray-900",
          )}
        >
          {message.content}
        </p>
      ))}
    </div>
  );
}

/** What the open chat is about, with a link to the case. */
function ScopeHeading({ scope, legacy }: { scope: AssistantScope | null; legacy: boolean }) {
  const label = useScopeLabel(scope);
  if (legacy) return <h1 className="min-w-0 flex-1 truncate font-serif text-[17px] font-bold text-gray-900">Older document chat</h1>;
  if (scope?.kind === "case") {
    return (
      <h1 className="min-w-0 flex-1 truncate font-serif text-[17px] font-bold text-gray-900">
        <Link
          href={`/cases/${scope.caseId}`}
          className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {label}
        </Link>
      </h1>
    );
  }
  return <h1 className="min-w-0 flex-1 truncate font-serif text-[17px] font-bold text-gray-900">{scope ? label : "Case Bot"}</h1>;
}

/** The full Case Bot page: chat list on the left, the open chat beside it.
 * The URL holds the selection: ?c=<id> for a chat, ?case=<id> or
 * ?scope=practice for a new one. */
export function AssistantPage() {
  const router = useRouter();
  const params = useSearchParams();
  const isMobile = useIsMobile();
  const [collapsed, setCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  /** A chat just created here, until the list knows about it. */
  const [created, setCreated] = useState<{ id: number; scope: AssistantScope } | null>(null);

  const selectedId = Number(params.get("c")) || null;
  const caseParam = Number(params.get("case")) || null;
  const scopeParam = params.get("scope");

  const defaultList = useConversationList("default");
  const practiceList = useConversationList("practice", PORTFOLIO_BOT_ENABLED);
  const remove = useDeleteConversation();

  const rows: Conversation[] = useMemo(
    () => [...(defaultList.data ?? []), ...(PORTFOLIO_BOT_ENABLED ? practiceList.data ?? [] : [])],
    [defaultList.data, practiceList.data],
  );
  const loading = defaultList.isLoading || (PORTFOLIO_BOT_ENABLED && practiceList.isLoading);
  const listError =
    defaultList.isError || (PORTFOLIO_BOT_ENABLED && practiceList.isError && !isPracticeUnavailable(practiceList.error));

  const row = selectedId !== null ? rows.find((item) => item.id === selectedId) : undefined;
  let scope: AssistantScope | null = null;
  let legacy = false;
  if (selectedId !== null) {
    if (row?.scope === "practice") scope = { kind: "practice" };
    else if (row && row.case_id !== null) scope = { kind: "case", caseId: row.case_id, caseTitle: row.case_title };
    else if (row) legacy = true;
    else if (created?.id === selectedId) scope = created.scope;
  } else if (caseParam !== null) {
    scope = { kind: "case", caseId: caseParam };
  } else if (scopeParam === "practice") {
    scope = { kind: "practice" };
  }
  const waiting = selectedId !== null && !row && scope === null && loading;
  const notFound = selectedId !== null && !row && scope === null && !loading;

  useEffect(() => {
    if (!isMobile || !drawerOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isMobile, drawerOpen]);

  function go(href: string, replace = false) {
    setDrawerOpen(false);
    if (replace) router.replace(href);
    else router.push(href);
  }

  function onConversationChange(id: number | null) {
    if (id !== null && id !== selectedId && scope !== null) {
      setCreated({ id, scope });
      go(`/assistant?c=${id}`, true);
    } else if (id === null && selectedId !== null) {
      go(assistantHref(scope, null));
    }
  }

  function onDelete(id: number) {
    remove.mutate(id, { onSuccess: () => id === selectedId && go("/assistant", true) });
  }

  const sidebar = (
    <ConversationSidebar
      conversations={rows}
      loading={loading}
      error={listError}
      onRetry={() => {
        void defaultList.refetch();
        if (PORTFOLIO_BOT_ENABLED) void practiceList.refetch();
      }}
      activeId={selectedId}
      onSelect={(id) => go(`/assistant?c=${id}`)}
      onNewChat={(next) => go(assistantHref(next, null))}
      onDelete={onDelete}
      deletingId={remove.isPending ? (remove.variables ?? null) : null}
      deleteError={remove.isError}
    />
  );

  return (
    <div className="flex h-full min-h-0 min-w-0 bg-surface">
      {isMobile ? (
        drawerOpen &&
        typeof document !== "undefined" &&
        createPortal(
          <div className="fixed inset-0 z-40">
            <div aria-hidden="true" className="absolute inset-0 bg-[rgba(14,26,44,0.5)]" onMouseDown={() => setDrawerOpen(false)} />
            <aside
              aria-label="Case Bot chats"
              className="absolute inset-y-0 left-0 w-[min(320px,85vw)] bg-surface pt-[env(safe-area-inset-top,0px)] shadow-2xl"
            >
              {sidebar}
            </aside>
          </div>,
          document.body,
        )
      ) : (
        !collapsed && (
          <aside aria-label="Case Bot chats" className="w-[280px] flex-shrink-0 border-r border-gray-200 bg-surface">
            {sidebar}
          </aside>
        )
      )}

      <section aria-label="Chat" className="flex min-w-0 flex-1 flex-col">
        <div className="flex min-h-[56px] items-center gap-2 border-b border-gray-200 px-3">
          <button
            type="button"
            aria-label={isMobile ? "Show chats" : collapsed ? "Show chats" : "Hide chats"}
            aria-expanded={isMobile ? drawerOpen : !collapsed}
            onClick={() => (isMobile ? setDrawerOpen(true) : setCollapsed((value) => !value))}
            className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-9 md:w-9"
          >
            <PanelLeft className="h-5 w-5" />
          </button>
          <ScopeHeading scope={scope} legacy={legacy} />
        </div>

        <div className="min-h-0 flex-1">
          {waiting ? (
            <p role="status" className="p-4 text-sm text-gray-500">
              Loading this chat.
            </p>
          ) : notFound ? (
            <div className="space-y-3 p-4">
              <p className="text-sm text-gray-700">That chat was not found. It may have been deleted.</p>
              <Button type="button" variant="secondary" size="sm" onClick={() => go("/assistant")}>
                Back to Case Bot
              </Button>
            </div>
          ) : legacy && selectedId !== null ? (
            <LegacyTranscript id={selectedId} />
          ) : scope === null ? (
            <div className="mx-auto max-w-md space-y-3 p-6 text-center">
              <MessagesSquare className="mx-auto h-10 w-10 text-gray-300" aria-hidden="true" />
              <h2 className="font-serif text-lg font-bold text-gray-900">Ask Case Bot</h2>
              <p className="text-sm text-gray-600">Pick a chat on the left, or start a new one.</p>
              <ScopeChoices onPick={(next) => go(assistantHref(next, null))} className="text-left" />
            </div>
          ) : (
            <AssistantConversation
              scope={scope}
              conversationId={selectedId}
              onConversationChange={onConversationChange}
              onChangeScope={(next) => go(assistantHref(next, null))}
              className="h-full"
            />
          )}
        </div>
      </section>
    </div>
  );
}
