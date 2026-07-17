"use client";

import { useMemo, useState } from "react";
import { useHearings } from "@/hooks/use-hearings";
import { useCases } from "@/hooks/use-cases";
import { CalendarMonth } from "@/components/calendar/calendar-month";
import { CalendarByCourt } from "@/components/calendar/calendar-by-court";
import { cn } from "@/lib/utils";

type View = "calendar" | "court";

export default function CalendarPage() {
  const [view, setView] = useState<View>("calendar");
  const { data: hearings = [], isLoading: hearingsLoading, error: hearingsError } = useHearings();
  const { data: cases = [], isLoading: casesLoading } = useCases("all");

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
    return (
      <div className="px-7 pt-7 pb-[60px] max-w-[1240px] mx-auto">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 rounded w-1/4 mb-6"></div>
          <div className="h-96 bg-gray-200 rounded-xl"></div>
        </div>
      </div>
    );
  }

  if (hearingsError) {
    return (
      <div className="px-7 pt-7 pb-[60px] max-w-[1240px] mx-auto">
        <div className="text-center py-12">
          <div className="text-[#b32e26] text-lg font-medium mb-2">
            Failed to load calendar
          </div>
          <div className="text-gray-500 text-sm">
            Please try refreshing the page
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
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
        <CalendarMonth hearings={hearings} caseMeta={caseMeta} />
      ) : (
        <CalendarByCourt hearings={upcomingHearings} caseMeta={caseMeta} />
      )}
    </div>
  );
}
