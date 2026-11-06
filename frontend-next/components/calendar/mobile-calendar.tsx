"use client";

import { useMemo, useRef, useState, type TouchEvent } from "react";
import { addDays, format, startOfWeek } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { CalendarByCourt } from "@/components/calendar/calendar-by-court";
import { CalendarMonth } from "@/components/calendar/calendar-month";
import { DayItems } from "@/components/calendar/day-items";
import { useTaskActions } from "@/components/calendar/use-task-actions";
import { riseIn } from "@/components/mobile/primitives";
import {
  ALL_KINDS,
  agendaDays,
  buildDayBuckets,
  dateToDayKey,
  dayKeyToDate,
  dayMarkerCounts,
  formatEventTimes,
  type CalendarItem,
  type CalendarKind,
} from "@/lib/calendar";
import { dateLabel } from "@/lib/dashboard/dates";
import { cn, pluralize, todayKey } from "@/lib/utils";
import type { CaseEvent, Hearing, Task } from "@/types";

type Mode = "agenda" | "month" | "court";
const MODES: { id: Mode; label: string }[] = [
  { id: "agenda", label: "Agenda" },
  { id: "month", label: "Month" },
  { id: "court", label: "By court" },
];

interface MobileCalendarProps {
  hearings: Hearing[];
  upcomingHearings: Hearing[];
  caseMeta: Map<number, { caseNumber: string; documentCount: number }>;
  tasks: Task[];
  events: CaseEvent[];
  kinds: ReadonlySet<CalendarKind>;
  onToggleKind: (kind: CalendarKind) => void;
}

/** The calendar on a phone. The default is an AGENDA: a week strip to pick a
 * day (swipe it for the next week), that day's hearings, deadlines and
 * appointments as cards, and what is coming after it. The month grid and the
 * by-court list are one tap away. */
export function MobileCalendar({
  hearings,
  upcomingHearings,
  caseMeta,
  tasks,
  events,
  kinds,
  onToggleKind,
}: MobileCalendarProps) {
  const [mode, setMode] = useState<Mode>("agenda");
  const [selected, setSelected] = useState(() => todayKey());
  const [direction, setDirection] = useState<1 | -1>(1);
  const taskActions = useTaskActions();
  const today = todayKey();

  const buckets = useMemo(() => buildDayBuckets({ hearings, tasks, events, kinds }), [hearings, tasks, events, kinds]);
  const weekStart = startOfWeek(dayKeyToDate(selected), { weekStartsOn: 1 });
  const weekDays = Array.from({ length: 7 }, (_, i) => dateToDayKey(addDays(weekStart, i)));
  const selectedItems = buckets.get(selected) ?? [];
  const later = useMemo(
    () => agendaDays(buckets, dateToDayKey(addDays(dayKeyToDate(selected), 1)), 21).slice(0, 8),
    [buckets, selected],
  );

  const shiftWeek = (weeks: number) => {
    setDirection(weeks > 0 ? 1 : -1);
    setSelected(dateToDayKey(addDays(dayKeyToDate(selected), weeks * 7)));
  };

  // Swipe the strip for the next or previous week.
  const touch = useRef<{ x: number; y: number } | null>(null);
  const onTouchStart = (e: TouchEvent) => {
    touch.current = { x: e.touches[0].clientX, y: e.touches[0].clientY };
  };
  const onTouchEnd = (e: TouchEvent) => {
    const start = touch.current;
    touch.current = null;
    if (!start) return;
    const dx = e.changedTouches[0].clientX - start.x;
    const dy = e.changedTouches[0].clientY - start.y;
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5) shiftWeek(dx < 0 ? 1 : -1);
  };

  const modeIndex = MODES.findIndex((m) => m.id === mode);

  return (
    <div data-testid="mobile-calendar" className="px-4 pb-6 pt-4">
      <header className="animate-rise-in motion-reduce:animate-none">
        <h1 className="!text-[26px] !font-bold !leading-[1.1] text-gray-900">Calendar</h1>
        <p className="mt-1 text-[13.5px] text-gray-600">
          {pluralize(upcomingHearings.length, "upcoming hearing")} across all cases
        </p>
      </header>

      <div
        role="tablist"
        aria-label="Calendar view"
        className="relative mt-3 grid grid-cols-3 rounded-[7px] border border-gray-200 bg-[var(--ci-paper-2)] p-[3px]"
      >
        <span
          aria-hidden="true"
          className="absolute bottom-[3px] left-[3px] top-[3px] w-[calc((100%-6px)/3)] rounded-[5px] bg-surface shadow-[0_1px_2px_rgba(14,26,44,0.14),0_0_0_1px_var(--ci-ink-14)] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] motion-reduce:transition-none"
          style={{ transform: `translateX(${modeIndex * 100}%)` }}
        />
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={mode === m.id}
            onClick={() => setMode(m.id)}
            className={cn("relative z-10 h-11 rounded-[5px] text-[13.5px] font-semibold transition-colors", mode === m.id ? "text-gray-900" : "text-gray-600")}
          >
            {m.label}
          </button>
        ))}
      </div>

      {mode === "agenda" && (
        <div className="mt-4">
          <div className="flex items-center gap-1">
            <h2 className="min-w-0 flex-1 truncate !text-[18px] !font-bold">{format(dayKeyToDate(selected), "MMMM yyyy")}</h2>
            <button
              type="button"
              onClick={() => setSelected(todayKey())}
              disabled={selected === todayKey()}
              className="h-10 rounded-full border border-gray-200 bg-surface px-3.5 text-[13px] font-semibold text-gray-800 transition-opacity disabled:opacity-40"
            >
              Today
            </button>
            <button type="button" aria-label="Previous week" onClick={() => shiftWeek(-1)} className="flex h-11 w-11 items-center justify-center rounded-full">
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button type="button" aria-label="Next week" onClick={() => shiftWeek(1)} className="flex h-11 w-11 items-center justify-center rounded-full">
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>

          <div
            key={weekDays[0]}
            role="group"
            aria-label="Week"
            data-no-swipe
            onTouchStart={onTouchStart}
            onTouchEnd={onTouchEnd}
            className={cn(
              "mt-1 grid grid-cols-7 gap-1 motion-reduce:animate-none",
              direction === 1 ? "animate-page-in" : "animate-page-in-reverse",
            )}
          >
            {weekDays.map((day, i) => {
              const d = dayKeyToDate(day);
              const counts = dayMarkerCounts(buckets.get(day));
              const isSelected = day === selected;
              const isToday = day === today;
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={isSelected}
                  aria-label={`${format(d, "EEEE d MMMM")}${isToday ? ", today" : ""}: ${
                    counts.hearing + counts.task + counts.event
                  } items`}
                  onClick={() => setSelected(day)}
                  style={{ animationDelay: `${i * 25}ms` }}
                  className={cn(
                    "flex h-[72px] animate-settle flex-col items-center justify-center rounded-[4px] border transition-colors motion-reduce:animate-none",
                    isSelected
                      ? "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]"
                      : isToday
                        ? "border-[var(--ci-seal)] bg-surface text-gray-900"
                        : "border-[var(--ci-ink-14)] bg-surface text-gray-900",
                  )}
                >
                  <span className="font-mono text-[10px] uppercase tracking-[0.08em] opacity-70">{format(d, "EEE")}</span>
                  <span className="font-serif text-[20px] font-bold leading-tight tabular-nums">{d.getDate()}</span>
                  <span className="mt-0.5 flex h-2 items-center justify-center gap-0.5" aria-hidden="true">
                    {counts.hearing > 0 && <i className="block h-[3px] w-3.5 rounded-sm bg-[var(--ci-warn)]" />}
                    {counts.event > 0 && <i className={cn("block h-[5px] w-[5px] rounded-full", isSelected ? "bg-[var(--ci-paper)]" : "bg-[var(--ci-ink)]")} />}
                    {counts.task > 0 && <i className="block h-[5px] w-[5px] rotate-45 bg-[var(--ci-seal)]" />}
                  </span>
                </button>
              );
            })}
          </div>

          <section aria-label="Selected day" className="mt-4">
            <div className="mb-2 flex items-center gap-2">
              <h3 className="!font-sans !text-[15px] !font-bold !tracking-normal text-gray-900">
                {dateLabel(selected, today) === "Today" || dateLabel(selected, today) === "Tomorrow"
                  ? `${dateLabel(selected, today)}, ${format(dayKeyToDate(selected), "EEEE d MMMM")}`
                  : format(dayKeyToDate(selected), "EEEE, d MMMM")}
              </h3>
              <span key={selectedItems.length} className="ci-chip ci-chip--none animate-settle motion-reduce:animate-none">
                {selectedItems.length}
              </span>
            </div>
            <div key={selected} className="flex animate-rise-in flex-col gap-2.5 motion-reduce:animate-none">
              {selectedItems.length === 0 ? (
                <p className="rounded-[3px] border border-dashed border-gray-200 px-4 py-6 text-center text-[14px] text-gray-500">
                  Nothing scheduled for this day.
                </p>
              ) : (
                <DayItems items={selectedItems} taskActions={taskActions} caseMeta={caseMeta} />
              )}
            </div>
          </section>

          {later.length > 0 && (
            <section aria-label="Coming up" className="mt-5">
              <h3 className="mb-2 !font-sans !text-[15px] !font-bold !tracking-normal text-gray-900">Coming up</h3>
              <ul className="overflow-hidden rounded-[3px] border border-[var(--ci-ink-14)] bg-surface shadow-card">
                {later.map(({ day, items }, i) => (
                  <li key={day} style={riseIn(i).style} className={cn("border-b border-gray-100 last:border-0", riseIn(i).className)}>
                    <button
                      type="button"
                      onClick={() => setSelected(day)}
                      className="block w-full px-3 py-2.5 text-left [--press-scale:0.99]"
                      aria-label={`Open ${format(dayKeyToDate(day), "EEEE d MMMM")}`}
                    >
                      <span className="flex items-center gap-2">
                        <span className="font-serif text-[14.5px] font-bold text-gray-900">{dateLabel(day, today)}</span>
                        <span className="ci-chip ci-chip--none ml-auto">{items.length}</span>
                      </span>
                      <span className="mt-1 block space-y-0.5">
                        {items.slice(0, 3).map((item) => (
                          <span key={item.key} className="flex items-center gap-2 text-[12.5px] text-gray-600">
                            <ItemMark item={item} />
                            <span className="min-w-0 truncate">{itemLabel(item)}</span>
                          </span>
                        ))}
                        {items.length > 3 && <span className="block text-[12px] text-gray-500">+{items.length - 3} more</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <Legend kinds={kinds} onToggle={onToggleKind} />
        </div>
      )}

      {mode === "month" && (
        <div key="month" className="mt-4 animate-rise-in motion-reduce:animate-none">
          <CalendarMonth
            hearings={hearings}
            caseMeta={caseMeta}
            tasks={tasks}
            events={events}
            kinds={kinds}
            onToggleKind={onToggleKind}
          />
        </div>
      )}

      {mode === "court" && (
        <div key="court" className="mt-4 animate-rise-in motion-reduce:animate-none">
          <CalendarByCourt hearings={upcomingHearings} caseMeta={caseMeta} />
        </div>
      )}
    </div>
  );
}

function itemLabel(item: CalendarItem): string {
  if (item.kind === "hearing") return item.hearing.case_title || "Hearing";
  if (item.kind === "task") return item.task.title;
  return `${item.event.title}${item.event.start_time ? ` · ${formatEventTimes(item.event.start_time, item.event.end_time)}` : ""}`;
}

function ItemMark({ item }: { item: CalendarItem }) {
  if (item.kind === "hearing") return <i aria-hidden="true" className="block h-[3px] w-3.5 flex-shrink-0 rounded-sm bg-[var(--ci-warn)]" />;
  if (item.kind === "event") return <i aria-hidden="true" className="block h-[6px] w-[6px] flex-shrink-0 rounded-full bg-[var(--ci-ink)]" />;
  return <i aria-hidden="true" className="block h-[6px] w-[6px] flex-shrink-0 rotate-45 bg-[var(--ci-seal)]" />;
}

const KIND_LABEL: Record<CalendarKind, string> = { hearing: "Hearings", task: "Deadlines", event: "Events" };

/** Which kinds show: three chips, each toggles its kind on and off. */
function Legend({ kinds, onToggle }: { kinds: ReadonlySet<CalendarKind>; onToggle: (kind: CalendarKind) => void }) {
  return (
    <div role="group" aria-label="Show" className="mt-5 flex flex-wrap gap-2">
      {ALL_KINDS.map((kind) => (
        <button
          key={kind}
          type="button"
          aria-pressed={kinds.has(kind)}
          onClick={() => onToggle(kind)}
          className={cn(
            "flex h-10 items-center gap-2 rounded-full border px-3.5 text-[13px] font-semibold transition-colors",
            kinds.has(kind) ? "border-[var(--ci-ink)] bg-surface text-gray-900" : "border-gray-200 bg-transparent text-gray-400 line-through",
          )}
        >
          <ItemMarkKind kind={kind} />
          {KIND_LABEL[kind]}
        </button>
      ))}
    </div>
  );
}

function ItemMarkKind({ kind }: { kind: CalendarKind }) {
  if (kind === "hearing") return <i aria-hidden="true" className="block h-[3px] w-3.5 rounded-sm bg-[var(--ci-warn)]" />;
  if (kind === "event") return <i aria-hidden="true" className="block h-[6px] w-[6px] rounded-full bg-[var(--ci-ink)]" />;
  return <i aria-hidden="true" className="block h-[6px] w-[6px] rotate-45 bg-[var(--ci-seal)]" />;
}
