"use client";

import { useMemo } from "react";
import { addMonths, endOfMonth, format, getDay, startOfMonth, subMonths } from "date-fns";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  dateToDayKey,
  dayMarkerCounts,
  type CalendarItem,
  type CalendarKind,
} from "@/lib/calendar";
import { dayCellSummary } from "@/lib/case-previews";
import { cn } from "@/lib/utils";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** The little shapes that tell the three kinds apart. Hearings keep the bar
 * the calendar has always drawn; appointments are round, deadlines are
 * diamonds. Used by the grid cells and the legend so they can't drift. */
export function KindMarker({ kind, className }: { kind: CalendarKind; className?: string }) {
  if (kind === "hearing") {
    return (
      <span
        aria-hidden="true"
        className={cn("inline-block h-2 w-4 rounded", className)}
        style={{ background: "var(--ci-warn)" }}
      />
    );
  }
  if (kind === "event") {
    return (
      <span
        aria-hidden="true"
        className={cn("inline-block h-2 w-2 rounded-full", className)}
        style={{ background: "var(--ci-ink)" }}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={cn("inline-block h-2 w-2 rotate-45", className)}
      style={{ background: "var(--ci-seal)" }}
    />
  );
}

const KIND_LABELS: Record<CalendarKind, string> = {
  hearing: "Hearings",
  event: "Events",
  task: "Deadlines & tasks",
};

const LEGEND_ORDER: CalendarKind[] = ["hearing", "event", "task"];

interface CalendarLegendProps {
  /** The kinds currently shown. */
  kinds: ReadonlySet<CalendarKind>;
  /** Present -> the legend entries are toggles. Absent -> a plain legend. */
  onToggle?: (kind: CalendarKind) => void;
  className?: string;
}

export function CalendarLegend({ kinds, onToggle, className }: CalendarLegendProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs", className)}>
      {LEGEND_ORDER.map((kind) => {
        const on = kinds.has(kind);
        const content = (
          <>
            <KindMarker kind={kind} className={on ? "" : "opacity-30"} />
            <span className={on ? "text-gray-700" : "text-gray-400 line-through"}>
              {KIND_LABELS[kind]}
            </span>
          </>
        );
        return onToggle ? (
          <button
            key={kind}
            type="button"
            aria-pressed={on}
            onClick={() => onToggle(kind)}
            className="inline-flex items-center gap-1.5 hover:text-gray-900"
          >
            {content}
          </button>
        ) : (
          <span key={kind} className="inline-flex items-center gap-1.5">
            {content}
          </span>
        );
      })}
    </div>
  );
}

/** One line for an item inside a day cell. */
function cellItemLabel(item: CalendarItem): string {
  if (item.kind === "hearing") return item.hearing.hearing_type_display || "Hearing";
  if (item.kind === "task") return item.task.title;
  return item.event.title;
}

interface MonthGridProps {
  /** First day of the month on display. */
  cursor: Date;
  onCursorChange: (cursor: Date) => void;
  /** Day key (YYYY-MM-DD) of the selected day. */
  selectedKey: string;
  onSelectDay: (key: string) => void;
  itemsByDay: ReadonlyMap<string, CalendarItem[]>;
  /** "markers" (default): bars and dots per kind -- the global calendar.
   * "items": each cell names its first items, and a day with more than the
   * limit ends in "+n more". */
  cellMode?: "markers" | "items";
  /** "+n more" was pressed on this day (items mode). */
  onMoreClick?: (key: string) => void;
  /** Taller cells, for the large month in the expanded view. */
  large?: boolean;
}

/** The month header, previous/next buttons and 7-column day grid -- the part
 * the global calendar and a case's calendar share. Presentational: the
 * caller owns the cursor, the selection and the data. */
export function MonthGrid({
  cursor,
  onCursorChange,
  selectedKey,
  onSelectDay,
  itemsByDay,
  cellMode = "markers",
  onMoreClick,
  large = false,
}: MonthGridProps) {
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

  return (
    <>
      <div className="px-3 sm:px-5 py-4 border-b border-gray-100 flex items-center justify-between">
        <div className="text-[15px] sm:text-base font-bold text-gray-900">
          {format(cursor, "MMMM yyyy")}
        </div>
        <div className="flex gap-1.5">
          <Button
            variant="secondary"
            size="sm"
            className="px-2.5 sm:px-3"
            onClick={() => onCursorChange(subMonths(cursor, 1))}
            aria-label="Previous month"
          >
            <ChevronLeft className="h-4 w-4 sm:hidden" />
            <span className="hidden sm:inline">Previous</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            className="px-2.5 sm:px-3"
            onClick={() => onCursorChange(addMonths(cursor, 1))}
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
            const dayKey = dateToDayKey(cell.date);
            const counts = dayMarkerCounts(itemsByDay.get(dayKey));
            const selected = dayKey === selectedKey;

            if (cellMode === "items") {
              const { visible, hidden } = dayCellSummary(itemsByDay.get(dayKey));
              const dayName = format(cell.date, "EEEE d MMMM");
              return (
                <div
                  key={dayKey}
                  className={cn(
                    "flex flex-col rounded-lg border transition-colors min-w-0",
                    large ? "min-h-[104px]" : "min-h-[84px]",
                    selected ? "border-primary bg-gray-100" : "border-transparent hover:bg-gray-50",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectDay(dayKey)}
                    aria-label={`${dayName}${describeCounts(counts)}`}
                    aria-pressed={selected}
                    className="w-full min-w-0 flex-1 rounded-lg px-1 py-1.5 text-left"
                  >
                    <div
                      className={cn(
                        "mb-1 text-center text-[12px] sm:text-[13px]",
                        selected ? "font-bold text-primary" : "text-gray-700",
                      )}
                    >
                      {format(cell.date, "d")}
                    </div>
                    {visible.length > 0 && (
                      <ul className="space-y-0.5">
                        {visible.map((item) => (
                          <li
                            key={item.key}
                            className="hidden items-center gap-1 text-[10px] leading-4 text-gray-700 sm:flex"
                          >
                            <KindMarker
                              kind={item.kind}
                              className="!h-1.5 flex-shrink-0 !w-2"
                            />
                            <span className="truncate">{cellItemLabel(item)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {/* Below `sm` the cell is too narrow for text: markers. */}
                    {visible.length > 0 && (
                      <div className="mt-1 flex justify-center gap-[3px] sm:hidden">
                        {visible.map((item) => (
                          <KindMarker key={item.key} kind={item.kind} className="!h-1.5 !w-1.5" />
                        ))}
                      </div>
                    )}
                  </button>
                  {hidden > 0 &&
                    (onMoreClick ? (
                      <button
                        type="button"
                        onClick={() => onMoreClick(dayKey)}
                        aria-label={`${hidden} more on ${dayName}`}
                        className="px-1 pb-1 text-left text-[10px] font-medium text-gray-600 underline underline-offset-2 hover:text-gray-900"
                      >
                        +{hidden} more
                      </button>
                    ) : (
                      <span className="px-1 pb-1 text-[10px] font-medium text-gray-600">
                        +{hidden} more
                      </span>
                    ))}
                </div>
              );
            }

            return (
              <button
                key={dayKey}
                type="button"
                onClick={() => onSelectDay(dayKey)}
                aria-label={`${format(cell.date, "EEEE d MMMM")}${describeCounts(counts)}`}
                aria-pressed={selected}
                className={cn(
                  "text-center rounded-lg py-2 px-0.5 min-h-[44px] sm:min-h-[58px] border transition-colors",
                  selected ? "border-primary bg-gray-100" : "border-transparent hover:bg-gray-50",
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
                {counts.hearing > 0 && (
                  <>
                    <div
                      className="mx-auto rounded"
                      style={{
                        height: `${6 + counts.hearing * 5}px`,
                        width: "70%",
                        background:
                          counts.hearing >= 2
                            ? "var(--ci-warn)"
                            : "color-mix(in srgb, var(--ci-warn) 45%, white)",
                      }}
                    />
                    <div className="text-[10px] text-gray-500 mt-1 hidden sm:block">
                      {counts.hearing}
                    </div>
                  </>
                )}
                {(counts.event > 0 || counts.task > 0) && (
                  <div className="flex justify-center gap-[3px] mt-1">
                    {Array.from({ length: Math.min(counts.event, 3) }, (_, n) => (
                      <KindMarker key={`e${n}`} kind="event" className="!h-1.5 !w-1.5" />
                    ))}
                    {Array.from({ length: Math.min(counts.task, 3) }, (_, n) => (
                      <KindMarker key={`t${n}`} kind="task" className="!h-1.5 !w-1.5" />
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

function describeCounts(counts: { hearing: number; task: number; event: number }): string {
  const parts = [
    counts.hearing && `${counts.hearing} hearing${counts.hearing === 1 ? "" : "s"}`,
    counts.event && `${counts.event} event${counts.event === 1 ? "" : "s"}`,
    counts.task && `${counts.task} deadline${counts.task === 1 ? "" : "s"}`,
  ].filter(Boolean);
  return parts.length ? `, ${parts.join(", ")}` : "";
}
