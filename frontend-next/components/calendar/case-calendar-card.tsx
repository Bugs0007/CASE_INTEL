"use client";

import { useEffect, useMemo, useState } from "react";
import { addDays, format, startOfMonth } from "date-fns";
import { CalendarDays, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ExpandableCard } from "@/components/ui/expandable-card";
import { CalendarLegend, MonthGrid } from "@/components/calendar/month-grid";
import { DayItems } from "@/components/calendar/day-items";
import { CaseEventDialog } from "@/components/calendar/case-event-dialog";
import { useTaskActions } from "@/components/calendar/use-task-actions";
import { useCaseEvents } from "@/hooks/use-case-events";
import { useTasks } from "@/hooks/use-tasks";
import {
  ALL_KINDS,
  agendaDays,
  buildDayBuckets,
  dateToDayKey,
  dayKeyToDate,
} from "@/lib/calendar";
import { cn, todayKey } from "@/lib/utils";
import type { CaseEvent, Hearing, UserPartyRole } from "@/types";

const KINDS = new Set(ALL_KINDS);
const AGENDA_DAYS = 30;

type View = "month" | "agenda";

interface CaseCalendarCardProps {
  caseId: number;
  /** The hearings the case page already loaded -- not fetched again here. */
  hearings: Hearing[];
  partyRole: UserPartyRole;
  /** Opens the Edit Details dialog, where the advocate's side is set. */
  onEditDetails: () => void;
}

/** One case's calendar: its hearings, the tasks and order deadlines due on
 * it, and the advocate's own events (arbitration, mediation, client
 * meetings...) -- in a month grid with the selected day beside it, or, on a
 * phone, an agenda of the next 30 days.
 *
 * A day cell names its first two items and ends in "+n more", which opens
 * the expanded view on that day: a large month with an agenda beside it. */
export function CaseCalendarCard({ caseId, hearings, partyRole, onEditDetails }: CaseCalendarCardProps) {
  // Same query (and cache entry) TasksCard reads.
  const { data: tasks = [] } = useTasks({ case_id: caseId });
  const { data: events = [] } = useCaseEvents({ case_id: caseId });
  const taskActions = useTaskActions();

  const [view, setView] = useState<View>("month");
  const [expandedOpen, setExpandedOpen] = useState(false);
  const [cursor, setCursor] = useState(() => startOfMonth(new Date()));
  const [selectedKey, setSelectedKey] = useState(() => todayKey());
  const [dialog, setDialog] = useState<{ open: boolean; event: CaseEvent | null; date: string }>({
    open: false,
    event: null,
    date: "",
  });

  // The 7-column grid is the hardest thing to fit on a phone, so below `md`
  // the agenda is the default. Set after mount, not in the initial state,
  // to avoid an SSR/hydration mismatch (the server has no viewport).
  useEffect(() => {
    if (window.innerWidth < 768) setView("agenda");
  }, []);

  const itemsByDay = useMemo(
    () => buildDayBuckets({ hearings, tasks, events, kinds: KINDS }),
    [hearings, tasks, events],
  );
  const selectedItems = itemsByDay.get(selectedKey) ?? [];
  const agenda = useMemo(
    () => agendaDays(itemsByDay, todayKey(), AGENDA_DAYS),
    [itemsByDay],
  );

  const openNewEvent = (date: string) => setDialog({ open: true, event: null, date });
  const openEditEvent = (event: CaseEvent) => setDialog({ open: true, event, date: event.date });
  const closeDialog = () => setDialog((d) => ({ ...d, open: false }));

  const itemList = (items: typeof selectedItems) => (
    <DayItems
      items={items}
      taskActions={taskActions}
      showCase={false}
      onEditEvent={openEditEvent}
    />
  );

  const dayHeading = format(dayKeyToDate(selectedKey), "EEEE, MMMM d");
  const selectedDay = (
    <section
      aria-label={dayHeading}
      className="border border-gray-100 rounded-xl"
    >
      <div className="px-4 py-3 border-b border-gray-100 text-sm font-bold text-gray-900">
        {dayHeading}
      </div>
      <div className="p-3 flex flex-col gap-2.5">
        {selectedItems.length === 0 ? (
          <div className="text-center py-4 text-sm text-gray-500">
            <p>Nothing on this day.</p>
            <button
              type="button"
              onClick={() => openNewEvent(selectedKey)}
              className="mt-1 text-xs font-medium text-gray-700 underline underline-offset-2 hover:text-gray-900"
            >
              Add an event on {format(dayKeyToDate(selectedKey), "d MMM")}
            </button>
          </div>
        ) : (
          itemList(selectedItems)
        )}
      </div>
    </section>
  );

  const agendaList =
    agenda.length === 0 ? (
      <p className="text-sm text-gray-500 py-2">Nothing in the next {AGENDA_DAYS} days.</p>
    ) : (
      <div className="space-y-4">
        {agenda.map(({ day, items }) => (
          <section key={day} aria-label={format(dayKeyToDate(day), "EEEE d MMMM")}>
            <h4 className="text-[11px] font-bold uppercase tracking-wide text-gray-400 mb-1.5">
              {day === todayKey()
                ? "Today"
                : day === dateToDayKey(addDays(new Date(), 1))
                  ? "Tomorrow"
                  : format(dayKeyToDate(day), "EEE, d MMM")}
            </h4>
            <div className="flex flex-col gap-2.5">{itemList(items)}</div>
          </section>
        ))}
      </div>
    );

  return (
    <>
      <ExpandableCard
        title="Calendar"
        icon={<CalendarDays className="h-4 w-4" />}
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => openNewEvent(view === "month" || expandedOpen ? selectedKey : todayKey())}
          >
            <Plus className="h-4 w-4 mr-1" />
            Add event
          </Button>
        }
        open={expandedOpen}
        onOpenChange={setExpandedOpen}
        bodyClassName="space-y-3"
      >
        {({ expanded }) => (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CalendarLegend kinds={KINDS} />
              {!expanded && (
                <div className="flex gap-1 bg-gray-100 rounded-lg p-1" role="group" aria-label="Calendar view">
                  {(["month", "agenda"] as const).map((v) => (
                    <button
                      key={v}
                      type="button"
                      aria-pressed={view === v}
                      onClick={() => setView(v)}
                      className={cn(
                        "h-7 px-3 rounded-md text-xs font-semibold transition-colors",
                        view === v ? "bg-white text-gray-900 shadow-sm" : "text-gray-500",
                      )}
                    >
                      {v === "month" ? "Month" : "Agenda"}
                    </button>
                  ))}
                </div>
              )}
            </div>

            {partyRole === "unknown" && (
              <p className="flex items-center gap-2 flex-wrap text-xs text-gray-500">
                Order deadlines appear here once your side (petitioner or respondent) is set.
                <button
                  type="button"
                  onClick={onEditDetails}
                  className="font-medium text-gray-700 underline underline-offset-2 hover:text-gray-900"
                >
                  Set your side
                </button>
              </p>
            )}

            {expanded ? (
              // The large month with the selected day and the next 30 days
              // beside it.
              <div className="grid grid-cols-1 @3xl:grid-cols-[minmax(0,1fr)_340px] gap-4 items-start">
                <div className="border border-gray-100 rounded-xl">
                  <MonthGrid
                    cursor={cursor}
                    onCursorChange={setCursor}
                    selectedKey={selectedKey}
                    onSelectDay={setSelectedKey}
                    itemsByDay={itemsByDay}
                    cellMode="items"
                    large
                    onMoreClick={setSelectedKey}
                  />
                </div>
                <div className="space-y-4">
                  {selectedDay}
                  <div>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">
                      Next {AGENDA_DAYS} days
                    </h3>
                    {agendaList}
                  </div>
                </div>
              </div>
            ) : view === "month" ? (
              <div className="grid grid-cols-1 @2xl:grid-cols-[1fr_300px] gap-4 items-start">
                <div className="border border-gray-100 rounded-xl">
                  <MonthGrid
                    cursor={cursor}
                    onCursorChange={setCursor}
                    selectedKey={selectedKey}
                    onSelectDay={setSelectedKey}
                    itemsByDay={itemsByDay}
                    cellMode="items"
                    onMoreClick={(key) => {
                      setSelectedKey(key);
                      setExpandedOpen(true);
                    }}
                  />
                </div>
                {selectedDay}
              </div>
            ) : (
              agendaList
            )}
          </>
        )}
      </ExpandableCard>

      <CaseEventDialog
        isOpen={dialog.open}
        onClose={closeDialog}
        caseId={caseId}
        event={dialog.event}
        defaultDate={dialog.date}
      />
    </>
  );
}
