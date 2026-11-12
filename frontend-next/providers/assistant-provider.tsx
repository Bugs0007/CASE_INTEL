"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { PORTFOLIO_BOT_ENABLED } from "@/lib/feature-flags";

/** What a Case Bot chat is about. A case title is carried when it is known
 * (picked from the chooser); otherwise the label looks it up. */
export type AssistantScope = { kind: "practice" } | { kind: "case"; caseId: number; caseTitle?: string | null };

interface AssistantContextValue {
  open: boolean;
  scope: AssistantScope | null;
  /** The popover's current chat; null is a new one. */
  conversationId: number | null;
  /** Opens the popover. On a case page it lands on that case. */
  openPopover: () => void;
  closePopover: () => void;
  /** Changing scope starts a new chat in it. */
  setScope: (scope: AssistantScope | null) => void;
  setConversationId: (id: number | null) => void;
}

const AssistantContext = createContext<AssistantContextValue | null>(null);

/** The case a /cases/<id> path is about, or null on any other page. */
export function caseIdFromPath(pathname: string | null): number | null {
  const match = /^\/cases\/(\d+)(?:\/|$)/.exec(pathname ?? "");
  return match ? Number(match[1]) : null;
}

/** Where the popover starts when nothing is remembered: the case page's case,
 * else the practice (when it is switched on), else nothing chosen yet. */
export function defaultScope(pathname: string | null): AssistantScope | null {
  const caseId = caseIdFromPath(pathname);
  if (caseId !== null) return { kind: "case", caseId };
  return PORTFOLIO_BOT_ENABLED ? { kind: "practice" } : null;
}

/** Holds the Case Bot popover's state above the pages, so the open chat is
 * still there after navigating. Chat content lives in the query cache and the
 * server, not here: only the choice of scope and conversation is kept. */
export function AssistantProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scope, setScopeState] = useState<AssistantScope | null>(null);
  const [conversationId, setConversationId] = useState<number | null>(null);

  const setScope = useCallback((next: AssistantScope | null) => {
    setScopeState(next);
    setConversationId(null);
  }, []);

  const openPopover = useCallback(() => {
    const pageCase = caseIdFromPath(pathname);
    const alreadyThere = scope?.kind === "case" && scope.caseId === pageCase;
    if (pageCase !== null && !alreadyThere) {
      setScopeState({ kind: "case", caseId: pageCase });
      setConversationId(null);
    } else if (scope === null) {
      setScopeState(defaultScope(pathname));
      setConversationId(null);
    }
    setOpen(true);
  }, [pathname, scope]);

  const closePopover = useCallback(() => setOpen(false), []);

  const value = useMemo(
    () => ({ open, scope, conversationId, openPopover, closePopover, setScope, setConversationId }),
    [open, scope, conversationId, openPopover, closePopover, setScope],
  );
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantContextValue {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistant must be used inside <AssistantProvider>");
  return ctx;
}
