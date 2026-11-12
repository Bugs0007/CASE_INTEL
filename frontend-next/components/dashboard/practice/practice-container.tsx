"use client";

import { useState } from "react";
import { isPracticeUnavailable, usePracticeOverview } from "@/hooks/use-practice-assistant";
import { usePracticeConversation } from "@/hooks/use-practice-conversation";
import { addDaysToKey, formatDayLong, todayDayKey, weekDayKeys, weekStartOf } from "./format";
import { PracticeSection } from "./practice-section";

/** The dashboard's practice block, wired to the server. It owns the shown
 * week, the selected day and the conversation; the parts below it are
 * presentational. */
export function PracticeContainer() {
  const [weekStart, setWeekStart] = useState(() => weekStartOf(todayDayKey()));
  const [selectedDay, setSelectedDay] = useState(() => todayDayKey());
  const [casePage, setCasePage] = useState(1);

  const overview = usePracticeOverview({ from: weekStart, to: addDaysToKey(weekStart, 6), casePage });

  const convo = usePracticeConversation();

  function askAboutDay(day: string) {
    convo.askAbout(day, `What is on ${formatDayLong(day)}?`);
  }

  function changeWeek(next: string) {
    setWeekStart(next);
    const today = todayDayKey();
    setSelectedDay(weekDayKeys(next).includes(today) ? today : next);
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
        messages: convo.messages,
        pending: convo.pending,
        error: convo.error,
        onRetry: convo.retry,
        draft: convo.draft,
        onDraftChange: convo.setDraft,
        onSend: convo.send,
        onChooseCase: convo.chooseCase,
        onConfirmInvoice: convo.confirm,
        onDismissAction: convo.dismissAction,
        confirmingFeeId: convo.confirmingFeeId,
      }}
    />
  );
}
