"use client";

import { useEffect, useMemo, useState } from "react";
import { useHearings } from "@/hooks/use-hearings";
import { useCases } from "@/hooks/use-cases";
import { useTasks } from "@/hooks/use-tasks";
import { useCaseEvents } from "@/hooks/use-case-events";
import { ALL_KINDS, type CalendarKind } from "@/lib/calendar";
import { CalendarMonth } from "@/components/calendar/calendar-month";
import { CalendarByCourt } from "@/components/calendar/calendar-by-court";
import { CalendarSkeleton } from "@/components/calendar/calendar-skeleton";
import { MobileCalendar } from "@/components/calendar/mobile-calendar";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { cn } from "@/lib/utils";

type View = "calendar" | "court";

export default function CalendarPage() {
  const [view, setView] = useState<View>("calendar");
  const isMobile = useIsMobile();
  // The 7-day-wide month grid is the hardest element to squeeze into a phone
  // screen, so mobile defaults to the already-mobile-friendly By Court list
  // instead. Done post-mount (not in the initial state) to avoid an SSR/
  // client hydration mismatch, since the server has no viewport to check.
  useEffect(() => {
    if (window.innerWidth < 768) {
      setView("court");
    }
  }, []);
  const { data: hearings = [], isLoading: hearingsLoading, error: hearingsError } = useHearings();
  const { data: cases = [], isLoading: casesLoading } = useCases("all");
  // Deadlines and the advocate's own events ride along on the month grid.
  // They never gate the page: if either fails to load, hearings still show.
  const { data: tasks = [] } = useTasks();
  const { data: events = [] } = useCaseEvents();
  const [kinds, setKinds] = useState<ReadonlySet<CalendarKind>>(() => new Set(ALL_KINDS));
  const toggleKind = (kind: CalendarKind) =>
    setKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  const caseMeta = useMemo(() => {
    const map = new Map<number, { caseNumber: string; documentCount: number }>();
    for (const c of cases) {
      map.set(c.id, { caseNumber: c.case_number, documentCount: c.document_count });
    }
    return map;
  }, [cases]);

  const upcomingHearings = useMemo(() => {
    const now = new Date();
    return hearings.filter(
      (h) => new Date(h.hearing_date) >= now && h.status !== "cancelled" && h.status !== "completed",
    );
  }, [hearings]);

  const isLoading = hearingsLoading || casesLoading;

  if (isLoading) {
    return <CalendarSkeleton />;
  }

  if (hearingsError) {
    return (
      <div className="px-4 sm:px-7 pt-5 sm:pt-7 pb-[60px] max-w-[1240px] mx-auto">
        <div className="text-center py-12">
          <div className="text-status-alert text-lg font-medium mb-2">
            Failed to load calendar
          </div>
          <div className="text-gray-500 text-sm">
            Please try refreshing the page
          </div>
        </div>
      </div>
    );
  }

  // A phone gets an agenda (week strip + the day's cards); month and by-court
  // are tabs inside it.
  if (isMobile) {
    return (
      <MobileCalendar
        hearings={hearings}
        upcomingHearings={upcomingHearings}
        caseMeta={caseMeta}
        tasks={tasks}
        events={events}
        kinds={kinds}
        onToggleKind={toggleKind}
      />
    );
  }

  return (
    <div className="p-4 sm:p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3.5">
        <div>
          <h1 className="text-page-title text-gray-900 mb-1.5">Calendar</h1>
          <p className="text-sm text-gray-600">
            {upcomingHearings.length} upcoming hearing
            {upcomingHearings.length === 1 ? "" : "s"} across all cases
          </p>
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setView("calendar")}
            className={cn(
              "h-8 px-4 rounded-md text-sm font-semibold transition-colors",
              view === "calendar" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500",
            )}
          >
            Calendar
          </button>
          <button
            onClick={() => setView("court")}
            className={cn(
              "h-8 px-4 rounded-md text-sm font-semibold transition-colors",
              view === "court" ? "bg-white text-gray-900 shadow-sm" : "text-gray-500",
            )}
          >
            By Court
          </button>
        </div>
      </div>

      {view === "calendar" ? (
        <CalendarMonth
          hearings={hearings}
          caseMeta={caseMeta}
          tasks={tasks}
          events={events}
          kinds={kinds}
          onToggleKind={toggleKind}
        />
      ) : (
        <CalendarByCourt hearings={upcomingHearings} caseMeta={caseMeta} />
      )}
    </div>
  );
}
