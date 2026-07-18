"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  addMonths,
  endOfMonth,
  format,
  getDay,
  isSameDay,
  parseISO,
  startOfMonth,
  subMonths,
} from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Hearing } from "@/types";

interface CalendarMonthProps {
  hearings: Hearing[];
  caseMeta: Map<number, { caseNumber: string; documentCount: number }>;
}

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export function CalendarMonth({ hearings, caseMeta }: CalendarMonthProps) {
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [selectedDate, setSelectedDate] = useState(() => new Date());

  const hearingsByDay = useMemo(() => {
    const map = new Map<string, Hearing[]>();
    for (const h of hearings) {
      const key = format(parseISO(h.hearing_date), "yyyy-MM-dd");
      const list = map.get(key) ?? [];
      list.push(h);
      map.set(key, list);
    }
    return map;
  }, [hearings]);

  const cells = useMemo(() => {
    const monthStart = startOfMonth(cursor);
    const monthEnd = endOfMonth(cursor);
    const startWeekday = getDay(monthStart);
    const daysInMonth = monthEnd.getDate();

    const out: { date: Date | null }[] = [];
    for (let i = 0; i < startWeekday; i++) out.push({ date: null });
    for (let d = 1; d <= daysInMonth; d++) {
      out.push({ date: new Date(cursor.getFullYear(), cursor.getMonth(), d) });
    }
    return out;
  }, [cursor]);

  const selectedHearings = (hearingsByDay.get(format(selectedDate, "yyyy-MM-dd")) ?? [])
    .slice()
    .sort((a, b) => a.hearing_date.localeCompare(b.hearing_date));

  return (
    <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5 items-start">
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm">
        <div className="px-3 sm:px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <div className="text-[15px] sm:text-base font-bold text-gray-900">
            {format(cursor, "MMMM yyyy")}
          </div>
          <div className="flex gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              className="px-2.5 sm:px-3"
              onClick={() => setCursor((c) => subMonths(c, 1))}
              aria-label="Previous month"
            >
              <ChevronLeft className="h-4 w-4 sm:hidden" />
              <span className="hidden sm:inline">Previous</span>
            </Button>
            <Button
              variant="secondary"
              size="sm"
              className="px-2.5 sm:px-3"
              onClick={() => setCursor((c) => addMonths(c, 1))}
              aria-label="Next month"
            >
              <ChevronRight className="h-4 w-4 sm:hidden" />
              <span className="hidden sm:inline">Next</span>
            </Button>
          </div>
        </div>
        <div className="p-2.5 sm:p-5">
          <div className="grid grid-cols-7 gap-1 sm:gap-1.5 mb-2">
            {WEEKDAY_LABELS.map((w) => (
              <div
                key={w}
                className="text-center text-[11px] font-bold uppercase tracking-wide text-gray-400 pb-1"
              >
                <span className="sm:hidden">{w[0]}</span>
                <span className="hidden sm:inline">{w}</span>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1 sm:gap-1.5">
            {cells.map((cell, i) => {
              if (!cell.date) return <div key={`blank-${i}`} />;
              const dayKey = format(cell.date, "yyyy-MM-dd");
              const dayHearings = hearingsByDay.get(dayKey) ?? [];
              const selected = isSameDay(cell.date, selectedDate);
              return (
                <button
                  key={dayKey}
                  onClick={() => setSelectedDate(cell.date as Date)}
                  className={cn(
                    "text-center rounded-lg py-2 px-0.5 min-h-[44px] sm:min-h-[58px] border transition-colors",
                    selected ? "border-[#323b83] bg-[#eef1fb]" : "border-transparent hover:bg-gray-50",
                  )}
                >
                  <div
                    className={cn(
                      "text-[12px] sm:text-[13px] mb-1 sm:mb-1.5",
                      selected ? "font-bold text-primary" : "text-gray-700",
                    )}
                  >
                    {format(cell.date, "d")}
                  </div>
                  {dayHearings.length > 0 && (
                    <>
                      <div
                        className="mx-auto rounded"
                        style={{
                          height: `${6 + dayHearings.length * 5}px`,
                          width: "70%",
                          background: dayHearings.length >= 2 ? "#323b83" : "#8d9bdb",
                        }}
                      />
                      <div className="text-[10px] text-gray-500 mt-1 hidden sm:block">
                        {dayHearings.length}
                      </div>
                    </>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="bg-white border border-gray-100 rounded-xl shadow-sm">
        <div className="px-5 py-4 border-b border-gray-100 text-[15px] font-bold text-gray-900">
          {format(selectedDate, "EEEE, MMMM d")}
        </div>
        <div className="p-4 flex flex-col gap-2.5">
          {selectedHearings.length === 0 ? (
            <div className="text-center py-5 text-sm text-gray-500">
              No hearings scheduled for this day.
            </div>
          ) : (
            selectedHearings.map((h) => {
              const meta = caseMeta.get(h.case);
              return (
                <div key={h.id} className="border border-gray-100 rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                    <span className="text-[13px] font-bold text-gray-900">
                      {format(parseISO(h.hearing_date), "h:mm a")}
                    </span>
                    <span
                      className={cn(
                        "inline-flex items-center h-[18px] px-1.5 rounded-full text-[10.5px] font-bold flex-shrink-0 whitespace-nowrap",
                        h.source === "ecourts"
                          ? "bg-[#ebf3fb] text-[#2f6fb0]"
                          : "bg-gray-100 text-gray-600",
                      )}
                    >
                      {h.source === "ecourts" ? "eCourts" : "Manual"}
                    </span>
                  </div>
                  <div className="text-sm font-semibold text-gray-900 mb-0.5">
                    {h.case_title}
                  </div>
                  <div className="text-xs text-gray-500 mb-2.5">
                    {h.location || "No location specified"}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-500">
                      {meta ? `${meta.documentCount} docs on file` : ""}
                    </span>
                    <Link href={`/cases/${h.case}`}>
                      <Button variant="secondary" size="sm">
                        View Case
                      </Button>
                    </Link>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
