"use client";

import Link from "next/link";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { format } from "date-fns";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { dayKeyToDate, formatEventTimes } from "@/lib/calendar";
import { cn } from "@/lib/utils";
import type { PracticeCalendarEntry, PracticeCalendarKind, PracticeCalendarWindow } from "@/types/practice";
import {
  addDaysToKey,
  formatAsOf,
  formatDayLong,
  formatWeekRange,
  humanize,
  todayDayKey,
  weekDayKeys,
} from "./format";
import { CALENDAR_ROUTE, entryHref } from "./routes";

// Same order as sortWithinDay in lib/calendar.ts: court dates, appointments, deadlines.
const KIND_ORDER: PracticeCalendarKind[] = ["hearing", "event", "task"];
const KIND_LABEL: Record<PracticeCalendarKind, { one: string; many: string; group: string }> = {
  hearing: { one: "hearing", many: "hearings", group: "Hearings" },
  task: { one: "deadline", many: "deadlines", group: "Deadlines" },
  event: { one: "event", many: "events", group: "Events" },
};
const KIND_DOT: Record<PracticeCalendarKind, string> = {
  hearing: "bg-primary",
  task: "bg-amber-500",
  event: "bg-emerald-600",
};
const QUIET_STATUSES = new Set(["scheduled", "pending", "open"]);

export interface PracticeWeekCalendarProps {
  /** The window for the shown week; null until it has loaded. */
  calendar: PracticeCalendarWindow | null;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  /** Monday of the shown week, YYYY-MM-DD. */
  weekStart: string;
  onWeekChange: (weekStart: string) => void;
  selectedDay: string;
  onSelectDay: (day: string) => void;
  /** Hands the day to the assistant. It never sends a message itself. */
  onAskAboutDay: (day: string) => void;
}

function countLabel(count: number, kind: PracticeCalendarKind): string {
  return `${count} ${count === 1 ? KIND_LABEL[kind].one : KIND_LABEL[kind].many}`;
}

function entryTime(entry: PracticeCalendarEntry): string | null {
  if (entry.kind === "event") return formatEventTimes(entry.start_time, entry.end_time);
  return entry.start_time ? formatEventTimes(entry.start_time, entry.end_time) : null;
}

function AgendaRow({ entry }: { entry: PracticeCalendarEntry }) {
  const time = entryTime(entry);
  const showStatus = !QUIET_STATUSES.has(entry.status);
  return (
    <li>
      <Link
        href={entryHref(entry)}
        className="flex min-h-[44px] flex-col gap-0.5 rounded-lg border border-gray-100 px-3 py-2 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {time && <span className="text-xs font-semibold text-gray-600">{time}</span>}
          <span className="min-w-0 break-words text-sm font-medium text-gray-900">{entry.label}</span>
          {showStatus && <span className="ci-chip ci-chip--none">{humanize(entry.status)}</span>}
          {entry.needs_review && <span className="ci-chip ci-chip--pending">Needs review</span>}
        </span>
        {entry.case_title && <span className="break-words text-xs text-gray-500">{entry.case_title}</span>}
      </Link>
    </li>
  );
}

/** A compact selectable week with the selected day's agenda underneath. Data
 * and every action come in as props. */
export function PracticeWeekCalendar({
  calendar,
  loading,
  error,
  onRetry,
  weekStart,
  onWeekChange,
  selectedDay,
  onSelectDay,
  onAskAboutDay,
}: PracticeWeekCalendarProps) {
  const today = todayDayKey();
  const days = weekDayKeys(weekStart);
  const dayEntries = (calendar?.entries ?? []).filter((entry) => entry.day === selectedDay);
  const asOf = calendar ? formatAsOf(calendar.as_of) : "";

  return (
    <Card aria-labelledby="practice-calendar-title">
      <CardHeader className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <CardTitle id="practice-calendar-title">This week</CardTitle>
          <p className="text-xs text-gray-500">{formatWeekRange(weekStart)}</p>
        </div>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            aria-label="Previous week"
            onClick={() => onWeekChange(addDaysToKey(weekStart, -7))}
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            aria-label="Next week"
            onClick={() => onWeekChange(addDaysToKey(weekStart, 7))}
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 px-3 sm:px-5">
        <div role="group" aria-label="Days of the week" className="grid grid-cols-7 gap-1">
          {days.map((day) => {
            const markers = calendar?.day_markers[day];
            const parts = KIND_ORDER.filter((kind) => (markers?.[kind] ?? 0) > 0).map((kind) =>
              countLabel(markers![kind], kind),
            );
            const isToday = day === today;
            const selected = day === selectedDay;
            return (
              <button
                key={day}
                type="button"
                aria-pressed={selected}
                aria-label={`${format(dayKeyToDate(day), "EEEE d MMMM")}${isToday ? ", today" : ""}, ${
                  parts.length ? parts.join(", ") : "nothing scheduled"
                }`}
                onClick={() => onSelectDay(day)}
                className={cn(
                  "flex min-h-[64px] min-w-0 flex-col items-center gap-1 rounded-lg border px-0.5 py-1.5 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                  selected ? "border-primary bg-primary/5" : "border-gray-200 hover:bg-gray-50",
                )}
              >
                <span className="text-[11px] uppercase text-gray-500">{format(dayKeyToDate(day), "EEE")}</span>
                <span
                  className={cn(
                    "flex h-6 w-6 items-center justify-center rounded-full text-sm font-semibold",
                    isToday ? "bg-primary text-page" : "text-gray-900",
                  )}
                >
                  {format(dayKeyToDate(day), "d")}
                </span>
                <span className="flex flex-wrap justify-center gap-x-1" aria-hidden="true">
                  {KIND_ORDER.filter((kind) => (markers?.[kind] ?? 0) > 0).map((kind) => (
                    <span key={kind} data-marker={kind} className="flex items-center gap-0.5 text-[10px] text-gray-600">
                      <span className={cn("h-1.5 w-1.5 rounded-full", KIND_DOT[kind])} />
                      {markers![kind]}
                    </span>
                  ))}
                </span>
              </button>
            );
          })}
        </div>

        <section aria-label={`Agenda for ${formatDayLong(selectedDay)}`} className="space-y-2">
          <h4 className="text-sm font-semibold text-gray-900">{formatDayLong(selectedDay)}</h4>

          {loading && (
            <div role="status" aria-busy="true" className="space-y-2">
              <p className="text-sm text-gray-500">Loading your calendar.</p>
              <div className="h-11 animate-pulse rounded-lg bg-gray-100" />
              <div className="h-11 animate-pulse rounded-lg bg-gray-100" />
            </div>
          )}

          {!loading && error && (
            <div role="alert" className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="text-sm text-red-800">The calendar could not be loaded.</p>
              <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
                Try again
              </Button>
            </div>
          )}

          {!loading && !error && calendar && (
            <>
              {calendar.truncated && (
                <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-900">
                  Showing {calendar.entries.length} of {calendar.total} items. Open the full calendar to see everything.
                </p>
              )}
              {calendar.total === 0 && !calendar.truncated ? (
                <p className="text-sm text-gray-500">Nothing is scheduled this week.</p>
              ) : dayEntries.length === 0 ? (
                <p className="text-sm text-gray-500">Nothing is scheduled on this day.</p>
              ) : (
                KIND_ORDER.map((kind) => {
                  const rows = dayEntries.filter((entry) => entry.kind === kind);
                  if (rows.length === 0) return null;
                  return (
                    <div key={kind} className="space-y-1">
                      <h5 className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                        {KIND_LABEL[kind].group}
                      </h5>
                      <ul className="space-y-1">
                        {rows.map((entry) => (
                          <AgendaRow key={`${entry.kind}-${entry.id}`} entry={entry} />
                        ))}
                      </ul>
                    </div>
                  );
                })
              )}
            </>
          )}
        </section>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="secondary" size="sm" onClick={() => onAskAboutDay(selectedDay)}>
              Ask about this day
            </Button>
            <Link
              href={CALENDAR_ROUTE}
              className="inline-flex h-11 items-center rounded-lg px-3 text-sm font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-8"
            >
              Open full calendar
            </Link>
          </div>
          {asOf && <p className="text-xs text-gray-500">Updated {asOf}</p>}
        </div>
      </CardContent>
    </Card>
  );
}
