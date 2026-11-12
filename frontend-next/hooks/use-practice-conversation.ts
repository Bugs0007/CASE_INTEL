"use client";

import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { apiErrorDetail } from "@/lib/api/client";
import { chatKeys } from "@/hooks/use-chat";
import {
  isPracticeUnavailable,
  useConfirmPracticeInvoice,
  useSendPracticeChat,
} from "@/hooks/use-practice-assistant";
import type { PracticeMessage } from "@/components/dashboard/practice/practice-assistant-panel";
import type { PracticeChatRequest } from "@/types/practice";

interface Options {
  /** Messages already in the conversation (a past chat being reopened). */
  initialMessages?: PracticeMessage[];
  /** The conversation to continue; undefined starts a new one. */
  conversationId?: number;
  /** The server named the conversation (first answer of a new chat). */
  onConversation?: (id: number) => void;
}

/** One practice-assistant conversation: its messages, the send and retry of
 * a question, the case chooser, and the invoice confirm. Used by the
 * dashboard block and by the Case Bot popover and page, so the three behave
 * the same. Nothing is sent except by `send` and `confirm`, which a person
 * triggers. */
export function usePracticeConversation({ initialMessages = [], conversationId: initialId, onConversation }: Options = {}) {
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<PracticeMessage[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [chatError, setChatError] = useState(false);
  /** The server answered 404: the assistant is switched off there. */
  const [unavailable, setUnavailable] = useState(false);
  const [confirmingFeeId, setConfirmingFeeId] = useState<number | null>(null);
  /** Set at once on a confirm, so a second click before the re-render sends nothing. */
  const sending = useRef(false);
  const conversationId = useRef<number | undefined>(initialId);
  /** The day "Ask about this day" picked; rides on the next send only. */
  const askedDay = useRef<string | undefined>(undefined);
  /** The send in flight or last failed; a retry sends this same request. */
  const lastRequest = useRef<PracticeChatRequest | null>(null);
  const localId = useRef(0);
  const nextId = () => `local-${(localId.current += 1)}`;

  const chat = useSendPracticeChat();
  const confirmInvoice = useConfirmPracticeInvoice();

  function dispatch(request: PracticeChatRequest) {
    lastRequest.current = request;
    setChatError(false);
    setUnavailable(false);
    chat.mutate(request, {
      onSuccess: (turn) => {
        const isNew = conversationId.current !== turn.conversation_id;
        conversationId.current = turn.conversation_id;
        lastRequest.current = null;
        setMessages((current) => [...current, { role: "assistant", id: nextId(), turn }]);
        queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
        if (isNew) onConversation?.(turn.conversation_id);
      },
      onError: (error) => {
        setChatError(true);
        setUnavailable(isPracticeUnavailable(error));
      },
    });
  }

  function send(query: string, caseId?: number) {
    if (chat.isPending) return;
    const request: PracticeChatRequest = {
      query,
      client_request_id: crypto.randomUUID(),
      ...(conversationId.current !== undefined ? { conversation_id: conversationId.current } : {}),
      ...(askedDay.current ? { selected_day: askedDay.current } : {}),
      ...(caseId !== undefined ? { case_id: caseId } : {}),
    };
    askedDay.current = undefined;
    setMessages((current) => [...current, { role: "user", id: nextId(), text: query }]);
    dispatch(request);
  }

  function retry() {
    if (lastRequest.current && !chat.isPending) dispatch(lastRequest.current);
  }

  /** Prefill the input for a day; the next send carries that day. */
  function askAbout(day: string, text: string) {
    askedDay.current = day;
    setDraft(text);
  }

  function chooseCase(caseId: number) {
    const candidate = [...messages]
      .reverse()
      .flatMap((m) => (m.role === "assistant" ? m.turn.case_candidates : []))
      .find((c) => c.id === caseId);
    if (!candidate) return;
    send([candidate.title, candidate.case_number].filter(Boolean).join(" "), caseId);
  }

  function dismissAction(messageId: string) {
    setMessages((current) =>
      current.map((m) =>
        m.role === "assistant" && m.id === messageId ? { ...m, turn: { ...m.turn, action_card: null } } : m,
      ),
    );
  }

  function confirm(feeId: number) {
    if (sending.current || confirmingFeeId !== null) return;
    const owner = messages.find((m) => m.role === "assistant" && m.turn.action_card?.fee_id === feeId);
    const card = owner && owner.role === "assistant" ? owner.turn.action_card : null;
    if (!card) return;
    const label = card.invoice_number ? `Invoice ${card.invoice_number}` : "The invoice";
    sending.current = true;
    setConfirmingFeeId(feeId);
    confirmInvoice.mutate(
      { feeId, caseId: card.case_id },
      {
        onSuccess: (result) => {
          // The existing endpoint resolves with sent=false when the server
          // only logged the email; say so rather than claiming delivery.
          const text = result.sent
            ? `Invoice sent to ${result.recipient || card.recipient_email || "the client"}.`
            : "Mail is not configured on this server. The send was recorded but no email went out.";
          setMessages((current) => [
            ...current.map((m) =>
              m.role === "assistant" && m.turn.action_card?.fee_id === feeId
                ? { ...m, turn: { ...m.turn, action_card: null } }
                : m,
            ),
            { role: "notice", id: nextId(), text, tone: result.sent ? "info" : "warning" },
          ]);
        },
        onError: (error) => {
          const reason = apiErrorDetail(error, "Try again in a moment.");
          setMessages((current) => [
            ...current,
            { role: "notice", id: nextId(), text: `${label} was not sent. ${reason}`, tone: "error" },
          ]);
        },
        onSettled: () => {
          sending.current = false;
          setConfirmingFeeId(null);
        },
      },
    );
  }

  return {
    messages,
    draft,
    setDraft,
    pending: chat.isPending,
    error: chatError,
    unavailable,
    confirmingFeeId,
    send,
    retry,
    askAbout,
    chooseCase,
    dismissAction,
    confirm,
  };
}
