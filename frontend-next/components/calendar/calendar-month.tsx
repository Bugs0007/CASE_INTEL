"use client";

import { useMemo, useState } from "react";
import { format, startOfMonth } from "date-fns";
import { CalendarLegend, MonthGrid } from "@/components/calendar/month-grid";
import { DayItems } from "@/components/calendar/day-items";
import { useTaskActions } from "@/components/calendar/use-task-actions";
import { ALL_KINDS, buildDayBuckets, dayKeyToDate, type CalendarKind } from "@/lib/calendar";
import { todayKey } from "@/lib/utils";
import type { CaseEvent, Hearing, Task } from "@/types";

interface CalendarMonthProps {
  hearings: Hearing[];
  caseMeta: Map<number, { caseNumber: string; documentCount: number }>;
  tasks?: Task[];
  events?: CaseEvent[];
  /** Which kinds are shown; all of them when omitted. */
  kinds?: ReadonlySet<CalendarKind>;
  /** Present -> the legend entries toggle a kind on and off. */
  onToggleKind?: (kind: CalendarKind) => void;
}

const EVERY_KIND: ReadonlySet<CalendarKind> = new Set(ALL_KINDS);

/** The global month calendar: hearings, plus the advocate's order deadlines,
 * tasks and case events, with the selected day's items beside the grid. */
export function CalendarMonth({
  hearings,
  caseMeta,
  tasks = [],
  events = [],
  kinds = EVERY_KIND,
  onToggleKind,
}: CalendarMonthProps) {
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [selectedKey, setSelectedKey] = useState(() => todayKey());
  const taskActions = useTaskActions();

  const itemsByDay = useMemo(
    () => buildDayBuckets({ hearings, tasks, events, kinds }),
    [hearings, tasks, events, kinds],
  );
  const selectedItems = itemsByDay.get(selectedKey) ?? [];

  return (
    <div className="space-y-3">
      <CalendarLegend kinds={kinds} onToggle={onToggleKind} />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-5 items-start">
        <div className="bg-white border border-gray-100 rounded-xl shadow-sm">
          <MonthGrid
            cursor={cursor}
            onCursorChange={setCursor}
            selectedKey={selectedKey}
            onSelectDay={setSelectedKey}
            itemsByDay={itemsByDay}
          />
        </div>

        <div className="bg-white border border-gray-100 rounded-xl shadow-sm">
          <div className="px-5 py-4 border-b border-gray-100 text-[15px] font-bold text-gray-900">
            {format(dayKeyToDate(selectedKey), "EEEE, MMMM d")}
          </div>
          <div className="p-4 flex flex-col gap-2.5">
            {selectedItems.length === 0 ? (
              <div className="text-center py-5 text-sm text-gray-500">
                {kinds.size === 1 && kinds.has("hearing")
                  ? "No hearings scheduled for this day."
                  : "Nothing scheduled for this day."}
              </div>
            ) : (
              <DayItems items={selectedItems} taskActions={taskActions} caseMeta={caseMeta} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
