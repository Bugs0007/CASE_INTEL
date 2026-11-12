"use client";

import { useRef, useState } from "react";
import { apiErrorDetail } from "@/lib/api/client";
import {
  isPracticeUnavailable,
  useConfirmPracticeInvoice,
  usePracticeOverview,
  useSendPracticeChat,
} from "@/hooks/use-practice-assistant";
import type { PracticeChatRequest } from "@/types/practice";
import { addDaysToKey, formatDayLong, todayDayKey, weekDayKeys, weekStartOf } from "./format";
import type { PracticeMessage } from "./practice-assistant-panel";
import { PracticeSection } from "./practice-section";

/** The dashboard's practice block, wired to the server. It owns the shown
 * week, the selected day and the conversation; the parts below it are
 * presentational. */
export function PracticeContainer() {
  const [weekStart, setWeekStart] = useState(() => weekStartOf(todayDayKey()));
  const [selectedDay, setSelectedDay] = useState(() => todayDayKey());
  const [casePage, setCasePage] = useState(1);

  const overview = usePracticeOverview({ from: weekStart, to: addDaysToKey(weekStart, 6), casePage });

  const [messages, setMessages] = useState<PracticeMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [chatError, setChatError] = useState(false);
  const [confirmingFeeId, setConfirmingFeeId] = useState<number | null>(null);
  /** Set at once on a confirm, so a second click before the re-render sends nothing. */
  const sending = useRef(false);
  const conversationId = useRef<number | undefined>(undefined);
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
    chat.mutate(request, {
      onSuccess: (turn) => {
        conversationId.current = turn.conversation_id;
        lastRequest.current = null;
        setMessages((current) => [...current, { role: "assistant", id: nextId(), turn }]);
      },
      onError: () => setChatError(true),
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

  function askAboutDay(day: string) {
    askedDay.current = day;
    setDraft(`What is on ${formatDayLong(day)}?`);
  }

  function changeWeek(next: string) {
    setWeekStart(next);
    const today = todayDayKey();
    setSelectedDay(weekDayKeys(next).includes(today) ? today : next);
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

  // The server has the assistant switched off: show nothing, not an error.
  if (isPracticeUnavailable(overview.error)) return null;

  return (
    <PracticeSection
      calendar={{
        calendar: overview.data?.calendar ?? null,
        loading: overview.isLoading,
        error: overview.isError,
        onRetry: () => overview.refetch(),
        weekStart,
        onWeekChange: changeWeek,
        selectedDay,
        onSelectDay: setSelectedDay,
        onAskAboutDay: askAboutDay,
      }}
      portfolio={{
        snapshot: overview.data?.portfolio ?? null,
        loading: overview.isLoading,
        error: overview.isError,
        onRetry: () => overview.refetch(),
        onPageChange: setCasePage,
      }}
      assistant={{
        messages,
        pending: chat.isPending,
        error: chatError,
        onRetry: retry,
        draft,
        onDraftChange: setDraft,
        onSend: send,
        onChooseCase: chooseCase,
        onConfirmInvoice: confirm,
        onDismissAction: dismissAction,
        confirmingFeeId,
      }}
    />
  );
}
