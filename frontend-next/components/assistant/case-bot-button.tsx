"use client";

import { useEffect, useRef, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { Bot, ChevronLeft, Maximize2, Plus, X } from "lucide-react";
import { AssistantConversation } from "@/components/assistant/assistant-conversation";
import { ScopeChip, useScopeLabel } from "@/components/assistant/scope-picker";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { assistantHref } from "@/lib/assistant";
import { useAssistant } from "@/providers/assistant-provider";

const ICON_BUTTON =
  "flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg text-gray-600 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-9 md:w-9";

/** The "Case Bot" button in the top bar, and the small chat it opens: a
 * popover under the button on a desktop, a full-height sheet on a phone. */
export function CaseBotButton() {
  const { open, scope, conversationId, openPopover, closePopover, setScope, setConversationId, chatKey, previous, backToPrevious } =
    useAssistant();
  const previousLabel = useScopeLabel(previous?.scope ?? null);
  const router = useRouter();
  const isMobile = useIsMobile();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Focus moves into the popover on open; closing puts it back on the button.
  useEffect(() => {
    if (open && !isMobile) panelRef.current?.focus({ preventScroll: true });
  }, [open, isMobile]);

  function close() {
    closePopover();
    buttonRef.current?.focus({ preventScroll: true });
  }

  function expand() {
    router.push(assistantHref(scope, conversationId));
    closePopover();
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
    }
  }

  const toolbar = (
    <div className="flex items-center justify-end gap-1.5 px-2 max-md:border-b max-md:border-gray-100 max-md:py-1">
      <button type="button" aria-label="New chat" title="New chat" onClick={() => setConversationId(null)} className={ICON_BUTTON}>
        <Plus className="h-[18px] w-[18px]" />
      </button>
      <button type="button" aria-label="Expand" title="Open full page" onClick={expand} className={ICON_BUTTON}>
        <Maximize2 className="h-4 w-4" />
      </button>
    </div>
  );

  const conversation = (
    <AssistantConversation
      key={chatKey}
      scope={scope}
      conversationId={conversationId}
      onConversationChange={setConversationId}
      onChangeScope={setScope}
      compact
      className="h-full"
    />
  );

  // What the chat is about, always visible beside the input, and the way
  // back to the chat a case page replaced.
  const backLink = previous && (
    <button
      type="button"
      onClick={backToPrevious}
      className="flex min-h-[44px] w-full items-center gap-1 border-b border-gray-100 px-3 text-left text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:min-h-8"
    >
      <ChevronLeft className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
      <span className="truncate">Back to {previousLabel}</span>
    </button>
  );
  const scopeBar = <ScopeChip scope={scope} onChange={setScope} className="border-t border-gray-100 px-3 py-1" />;

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => (open ? close() : openPopover())}
        aria-label="Case Bot"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Case Bot"
        className="ci-btn ci-btn--line h-11 w-11 justify-center !p-0 max-md:!border-transparent md:h-9 md:w-auto md:gap-2 md:!px-3"
      >
        <Bot className="h-[20px] w-[20px] md:h-4 md:w-4" strokeWidth={1.8} />
        <span className="text-sm font-semibold max-md:hidden">Case Bot</span>
      </button>

      {open && isMobile && (
        <BottomSheet open onClose={close} label="Case Bot" size="full" bodyClassName="flex flex-col overflow-hidden">
          {toolbar}
          {backLink}
          <div className="min-h-0 flex-1">{conversation}</div>
          {scopeBar}
        </BottomSheet>
      )}

      {open &&
        !isMobile &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={panelRef}
            role="dialog"
            aria-label="Case Bot"
            tabIndex={-1}
            onKeyDown={onKeyDown}
            className="fixed right-4 top-[72px] z-40 flex h-[560px] max-h-[calc(100dvh-88px)] w-[400px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-xl border border-gray-200 bg-surface shadow-2xl outline-none"
          >
            <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-3 pt-2">
              <h2 className="font-serif text-[15px] font-bold text-gray-900">Case Bot</h2>
              <div className="flex items-center gap-1">
                {toolbar}
                <button type="button" aria-label="Close Case Bot" onClick={close} className={ICON_BUTTON}>
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
            {backLink}
            <div className="min-h-0 flex-1">{conversation}</div>
            {scopeBar}
          </div>,
          document.body,
        )}
    </>
  );
}
