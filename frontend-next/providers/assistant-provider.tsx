"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { PORTFOLIO_BOT_ENABLED } from "@/lib/feature-flags";

/** What a Case Bot chat is about. A case title is carried when it is known
 * (picked from the chooser); otherwise the label looks it up. */
export type AssistantScope =
  | { kind: "practice" }
  | { kind: "case"; caseId: number; caseTitle?: string | null; caseNumber?: string | null };

/** A question handed to a chat from outside (the dashboard's ask bar, "Ask
 * about this day", "Ask in this case"). `send` questions go out as soon as the
 * chat opens; the others only fill the input. */
export interface AssistantAsk {
  id: number;
  scope: AssistantScope;
  question: string;
  selectedDay?: string;
  send: boolean;
}

/** The chat the popover was on before a case page took it over. */
export interface PreviousChat {
  scope: AssistantScope;
  conversationId: number | null;
}

export function sameScope(a: AssistantScope | null, b: AssistantScope | null): boolean {
  if (a === null || b === null) return a === b;
  if (a.kind !== b.kind) return false;
  return a.kind === "practice" || (b.kind === "case" && a.caseId === b.caseId);
}

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
  /** A question waiting for the chat it is for. */
  ask: AssistantAsk | null;
  /** Changes whenever openWith starts a fresh chat, so the chat remounts. */
  chatKey: number;
  /** Opens the popover on a new chat in `scope` with the question; sent unless `send` is false. */
  openWith: (request: { scope: AssistantScope; question: string; selectedDay?: string; send?: boolean }) => void;
  /** Leaves a question for a chat that is about to open; nothing is sent. */
  prefill: (scope: AssistantScope, question: string) => void;
  /** The chat that took the question calls this so it is used once. */
  consumeAsk: (id: number) => void;
  /** Set when opening on a case page replaced a different remembered chat. */
  previous: PreviousChat | null;
  backToPrevious: () => void;
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

  const [ask, setAsk] = useState<AssistantAsk | null>(null);
  const [chatKey, setChatKey] = useState(0);
  const [previous, setPrevious] = useState<PreviousChat | null>(null);
  const askCounter = useRef(0);

  const setScope = useCallback((next: AssistantScope | null) => {
    setScopeState(next);
    setConversationId(null);
    setPrevious(null);
  }, []);

  const openPopover = useCallback(() => {
    const pageCase = caseIdFromPath(pathname);
    const alreadyThere = scope?.kind === "case" && scope.caseId === pageCase;
    if (pageCase !== null && !alreadyThere) {
      // Never carry another case's chat onto this page: start on this case
      // and keep the old chat one click away.
      setPrevious(scope ? { scope, conversationId } : null);
      setScopeState({ kind: "case", caseId: pageCase });
      setConversationId(null);
    } else if (scope === null) {
      setScopeState(defaultScope(pathname));
      setConversationId(null);
    }
    setOpen(true);
  }, [pathname, scope, conversationId]);

  const closePopover = useCallback(() => setOpen(false), []);

  const openWith = useCallback(
    ({ scope: next, question, selectedDay, send = true }: Parameters<AssistantContextValue["openWith"]>[0]) => {
      askCounter.current += 1;
      setAsk({ id: askCounter.current, scope: next, question, selectedDay, send });
      setScopeState(next);
      setConversationId(null);
      setPrevious(null);
      setChatKey((key) => key + 1);
      setOpen(true);
    },
    [],
  );

  const prefill = useCallback((next: AssistantScope, question: string) => {
    askCounter.current += 1;
    setAsk({ id: askCounter.current, scope: next, question, send: false });
  }, []);

  const consumeAsk = useCallback((id: number) => setAsk((current) => (current?.id === id ? null : current)), []);

  const backToPrevious = useCallback(() => {
    if (!previous) return;
    setScopeState(previous.scope);
    setConversationId(previous.conversationId);
    setPrevious(null);
    setChatKey((key) => key + 1);
  }, [previous]);

  const value = useMemo(
    () => ({
      open, scope, conversationId, openPopover, closePopover, setScope, setConversationId,
      ask, chatKey, openWith, prefill, consumeAsk, previous, backToPrevious,
    }),
    [open, scope, conversationId, openPopover, closePopover, setScope, ask, chatKey, openWith, prefill, consumeAsk, previous, backToPrevious],
  );
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

export function useAssistant(): AssistantContextValue {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistant must be used inside <AssistantProvider>");
  return ctx;
}
