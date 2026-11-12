"use client";

import { useState } from "react";
import { isPracticeUnavailable, usePracticeOverview } from "@/hooks/use-practice-assistant";
import { useAssistant } from "@/providers/assistant-provider";
import { addDaysToKey, formatDayLong, todayDayKey, weekDayKeys, weekStartOf } from "./format";
import { PracticeSection } from "./practice-section";

/** The dashboard's practice block, wired to the server. It owns the shown
 * week and the selected day; the parts below it are presentational. Questions
 * go to the Case Bot, which opens in "Your practice" scope and sends them. */
export function PracticeContainer() {
  const [weekStart, setWeekStart] = useState(() => weekStartOf(todayDayKey()));
  const [selectedDay, setSelectedDay] = useState(() => todayDayKey());
  const { openWith } = useAssistant();

  // The first page of cases is all the summary needs: it names five of them.
  const overview = usePracticeOverview({ from: weekStart, to: addDaysToKey(weekStart, 6), casePage: 1 });

  function askAboutDay(day: string) {
    openWith({ scope: { kind: "practice" }, question: `What is on ${formatDayLong(day)}?`, selectedDay: day });
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
      }}
      onAsk={(question) => openWith({ scope: { kind: "practice" }, question })}
    />
  );
}
