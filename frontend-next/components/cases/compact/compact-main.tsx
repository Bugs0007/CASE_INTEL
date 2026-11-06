"use client";

import { useMemo, useState } from "react";
import { CalendarDays, FileText, Gavel, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CompactCard } from "@/components/cases/compact/compact-card";
import { OrderOverviewCard } from "@/components/cases/order-overview";
import { CaseCalendarCard } from "@/components/calendar/case-calendar-card";
import { CaseEventDialog } from "@/components/calendar/case-event-dialog";
import { HearingItem } from "@/components/hearings/hearings-list";
import { HearingDigestDialog } from "@/components/hearings/hearing-digest-dialog";
import { groupOrdersByDate, hearingDateKey } from "@/hooks/use-court-orders";
import { useCaseEvents } from "@/hooks/use-case-events";
import { useTasks } from "@/hooks/use-tasks";
import { buildDayBuckets, dayMarkerCounts } from "@/lib/calendar";
import { latestOrderForOverview, matchesQuery, ordersWithOverview } from "@/lib/case-previews";
import {
  allHearingRows,
  comingUpRows,
  compactHearingRows,
  filterHearingRows,
  miniMonthWeeks,
  weekStrip,
  type HearingFilter,
  type HearingRow,
} from "@/lib/case-page-rows";
import { dateLabel, dayKeyToDate, dayMonth, istDayKey, shortDay } from "@/lib/dashboard/dates";
import { cn, todayKey } from "@/lib/utils";
import type { Case, CourtOrder, Hearing, OrderSummary } from "@/types";

// ---------------------------------------------------------------------------
// Order Overview
// ---------------------------------------------------------------------------

/** The text for the direction box: your side's when the side is known, else
 * both sides as the order states them. */
export function directionsOf(summary: OrderSummary): { label: string; text: string } | null {
  if (summary.status !== "summarized") return null;
  if (summary.your_side_directions !== null) {
    const text = summary.your_side_directions.join(" ");
    return {
      label: summary.your_side_label ?? "Your side",
      text: text || "No directions for your side in this order.",
    };
  }
  const pet = summary.petitioner_directions.join(" ");
  const res = summary.respondent_directions.join(" ");
  if (pet && res) return { label: "Directions", text: `Petitioner: ${pet} · Respondent: ${res}` };
  if (res) return { label: "Respondent", text: res };
  if (pet) return { label: "Petitioner", text: pet };
  return null;
}

function nextDateLine(summary: OrderSummary, currentNext: string | null | undefined): React.ReactNode {
  if (!summary.next_date) return null;
  const passed = summary.next_date < todayKey();
  const when = `${dayMonth(summary.next_date)} ${summary.next_date.slice(0, 4)}`;
  if (!passed) {
    return (
      <>
        Next date: <span className="font-semibold text-gray-900">{when}</span>
        {summary.next_date_purpose ? ` — ${summary.next_date_purpose}` : ""}
      </>
    );
  }
  return (
    <>
      Next date in this order: <span className="line-through">{when}</span> (passed) ·{" "}
      {currentNext
        ? `current next hearing ${dayMonth(currentNext.slice(0, 10))} ${currentNext.slice(0, 4)} (Court Tracking)`
        : "see Court Tracking for the current next hearing"}
    </>
  );
}

export function CompactOrderOverview({
  caseItem,
  orders,
  onViewOrder,
  viewingOrderId,
  onSetSide,
}: {
  caseItem: Case;
  orders: CourtOrder[];
  onViewOrder: (orderId: number) => void;
  viewingOrderId?: number;
  onSetSide: () => void;
}) {
  const order = latestOrderForOverview(orders);
  const summary = order?.summary;
  const ready = !!order && !!summary && summary.status !== "pending";
  const all = ordersWithOverview(orders);
  const directions = summary ? directionsOf(summary) : null;
  const roleUnknown = caseItem.user_party_role === "unknown";

  return (
    <CompactCard
      id="order-overview"
      title="Order Overview"
      icon={<Gavel className="h-4 w-4" />}
      titleExtra={order?.order_date ? `${dayMonth(order.order_date)} ${order.order_date.slice(0, 4)}` : undefined}
      actions={
        order?.has_file ? (
          <Button variant="secondary" size="sm" onClick={() => onViewOrder(order.id)} disabled={viewingOrderId === order.id}>
            {viewingOrderId === order.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
            Read the order
          </Button>
        ) : undefined
      }
      dialog={all.length > 0 ? { count: all.length, children: <OrderOverviewCard orders={orders} currentNextHearing={caseItem.next_hearing_date} onViewOrder={onViewOrder} viewingOrderId={viewingOrderId} /> } : undefined}
    >
      {!ready || !summary ? (
        <p className="px-4 py-3 text-[13.5px] text-gray-500">No order summary yet.</p>
      ) : (
        <div className="flex flex-col gap-1 px-4 py-2">
          <div className={cn("grid gap-4", directions && "grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]")}>
            <div className="min-w-0">
              <p className="line-clamp-3 text-[13.5px] leading-[1.4] text-gray-900">
                {summary.status === "failed"
                  ? "Summary unavailable. Open the order to read it."
                  : summary.what_happened}
              </p>
              {roleUnknown && directions && (
                <p className="mt-1 text-xs text-gray-500">
                  Your side isn&apos;t recorded, so both sides are shown.{" "}
                  <button type="button" onClick={onSetSide} className="font-semibold text-gray-800 underline">
                    Set it
                  </button>
                </p>
              )}
            </div>
            {directions && (
              <div className="min-w-0 rounded border border-gray-200 bg-page px-2.5 py-1.5">
                <div className="font-mono text-[11px] uppercase leading-none tracking-[0.08em] text-gray-500">
                  {directions.label}
                </div>
                <p className="mt-0.5 line-clamp-3 text-[13px] leading-[1.35] text-gray-900">{directions.text}</p>
              </div>
            )}
          </div>
          {summary.next_date && (
            <div className="truncate border-t border-gray-100 pt-1 text-xs text-gray-500">
              {nextDateLine(summary, caseItem.next_hearing_date)}
            </div>
          )}
        </div>
      )}
    </CompactCard>
  );
}

// ---------------------------------------------------------------------------
// Hearings & orders
// ---------------------------------------------------------------------------

const DOT: Record<HearingRow["tone"], string> = {
  upcoming: "bg-[var(--ci-warn)]",
  passed: "bg-gray-400",
  order: "bg-[var(--ci-listed)]",
  other: "bg-gray-400",
};

function HearingLine({
  row,
  onViewOrder,
  viewingOrderId,
  trailing,
  roomy,
}: {
  row: HearingRow;
  onViewOrder: (orderId: number) => void;
  viewingOrderId?: number;
  trailing?: React.ReactNode;
  roomy?: boolean;
}) {
  const { order } = row;
  return (
    <li
      className={cn(
        "flex items-center gap-3 border-b border-gray-100 px-4 last:border-b-0",
        roomy ? "min-h-[52px] py-2" : "h-10",
        row.isNext && "bg-[color-mix(in_srgb,var(--ci-warn)_9%,white)]",
      )}
    >
      <span className={cn("h-2.5 w-2.5 flex-shrink-0 rounded-full", DOT[row.tone])} aria-hidden="true" />
      <div className={cn("min-w-0 flex-1", roomy ? "" : "flex items-center gap-4")}>
        <div className="w-[104px] flex-shrink-0 text-[13.5px] font-bold text-gray-900">
          {dayMonth(row.day)} {row.day.slice(0, 4)}
        </div>
        <div className="min-w-0 flex-1 truncate text-[13px] text-gray-600">{row.text || "—"}</div>
      </div>
      <span className="flex-shrink-0 font-mono text-[11px] tracking-[0.06em] text-gray-500">{row.status}</span>
      {order?.has_file && (
        <Button
          variant="secondary"
          size="sm"
          className="flex-shrink-0"
          onClick={() => onViewOrder(order.id)}
          disabled={viewingOrderId === order.id}
          aria-label={`Order of ${dayMonth(row.day)} ${row.day.slice(0, 4)}`}
        >
          {viewingOrderId === order.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
          Order
        </Button>
      )}
      {trailing}
    </li>
  );
}

interface CompactHearingsProps {
  caseId: number;
  hearings: Hearing[];
  orders: CourtOrder[];
  rows: number;
  isLoading: boolean;
  onAddHearing: () => void;
  onEditHearing: (hearing: Hearing) => void;
  onDeleteHearing: (id: number) => void;
  deletingId?: number;
  onViewOrder: (orderId: number) => void;
  viewingOrderId?: number;
  /** One plain line under the rows about the order check (see order sync). */
  statusLine?: React.ReactNode;
}

export function CompactHearings({
  caseId,
  hearings,
  orders,
  rows,
  isLoading,
  onAddHearing,
  onEditHearing,
  onDeleteHearing,
  deletingId,
  onViewOrder,
  viewingOrderId,
  statusLine,
}: CompactHearingsProps) {
  const today = istDayKey();
  const { rows: shown, total } = useMemo(
    () => compactHearingRows(hearings, orders, today, rows),
    [hearings, orders, today, rows],
  );
  const all = useMemo(() => allHearingRows(hearings, orders, today), [hearings, orders, today]);
  const byDate = useMemo(() => groupOrdersByDate(orders), [orders]);

  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<HearingFilter>("all");
  const [query, setQuery] = useState("");
  const [detailId, setDetailId] = useState<number | null>(null);
  const [prepId, setPrepId] = useState<number | null>(null);

  const counts = {
    all: all.length,
    upcoming: filterHearingRows(all, "upcoming").length,
    passed: filterHearingRows(all, "passed").length,
    orders: filterHearingRows(all, "orders").length,
  };
  const visible = filterHearingRows(all, filter).filter((r) =>
    matchesQuery(query, `${dayMonth(r.day)} ${r.day.slice(0, 4)}`, r.text, r.status, r.hearing.location, r.hearing.judge, r.hearing.purpose),
  );

  const chips: { key: HearingFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "upcoming", label: "Upcoming" },
    { key: "passed", label: "Passed" },
    { key: "orders", label: "Orders" },
  ];

  return (
    <>
      <CompactCard
        id="hearings"
        className="min-h-0 flex-1"
        title="Hearings & orders"
        icon={<Gavel className="h-4 w-4" />}
        count={total}
        viewAll={total > shown.length ? total : undefined}
        open={open}
        onOpenChange={(next) => {
          setOpen(next);
          if (!next) {
            setDetailId(null);
            setQuery("");
          }
        }}
        dialog={{
          count: total,
          actions: (
            <Button variant="secondary" size="sm" onClick={onAddHearing}>
              <Plus className="h-3.5 w-3.5" />
              Add hearing
            </Button>
          ),
          toolbar: (
            <div className="flex flex-wrap items-center gap-2">
              <div role="group" aria-label="Filter hearings" className="flex flex-wrap gap-1.5">
                {chips.map((chip) => (
                  <button
                    key={chip.key}
                    type="button"
                    aria-pressed={filter === chip.key}
                    onClick={() => setFilter(chip.key)}
                    className={cn(
                      "h-8 rounded-full border px-3 text-xs font-bold",
                      filter === chip.key
                        ? "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]"
                        : "border-gray-200 bg-surface text-gray-600 hover:border-[var(--ci-ink)]",
                    )}
                  >
                    {chip.label} {counts[chip.key]}
                  </button>
                ))}
              </div>
              <Input
                type="search"
                aria-label="Search hearings"
                placeholder="Search hearings"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="ml-auto h-8 w-full sm:w-60"
              />
            </div>
          ),
          footer: `${total} hearing${total === 1 ? "" : "s"} · fee and travel details open from each row`,
          children: (
            <ul className="-mx-4 -my-4 sm:-mx-5">
              {visible.length === 0 && <li className="px-5 py-6 text-sm text-gray-500">No hearings match.</li>}
              {visible.map((row) => (
                <div key={row.hearing.id}>
                  <HearingLine
                    row={row}
                    roomy
                    onViewOrder={onViewOrder}
                    viewingOrderId={viewingOrderId}
                    trailing={
                      <Button
                        variant="ghost"
                        size="sm"
                        className="flex-shrink-0"
                        aria-expanded={detailId === row.hearing.id}
                        onClick={() => setDetailId(detailId === row.hearing.id ? null : row.hearing.id)}
                      >
                        Details
                      </Button>
                    }
                  />
                  {detailId === row.hearing.id && (
                    <div className="border-b border-gray-100 bg-page px-4 py-3">
                      <HearingItem
                        hearing={row.hearing}
                        caseId={caseId}
                        isUpcoming={row.tone === "upcoming"}
                        onPrepare={row.tone === "upcoming" ? setPrepId : undefined}
                        onEdit={onEditHearing}
                        onDelete={onDeleteHearing}
                        isDeleting={deletingId === row.hearing.id}
                        orders={byDate.get(hearingDateKey(row.hearing.hearing_date))}
                        onViewOrder={onViewOrder}
                        viewingOrderId={viewingOrderId}
                      />
                    </div>
                  )}
                </div>
              ))}
            </ul>
          ),
        }}
        actions={
          total === 0 ? (
            <Button variant="secondary" size="sm" onClick={onAddHearing}>
              <Plus className="h-3.5 w-3.5" />
              Add hearing
            </Button>
          ) : undefined
        }
      >
        {isLoading ? (
          <p className="px-4 py-3 text-sm text-gray-500">Loading hearings…</p>
        ) : shown.length === 0 ? (
          <p className="px-4 py-3 text-[13.5px] text-gray-500">No hearings scheduled.</p>
        ) : (
          <ul>
            {shown.map((row) => (
              <HearingLine key={row.hearing.id} row={row} onViewOrder={onViewOrder} viewingOrderId={viewingOrderId} />
            ))}
          </ul>
        )}
        {statusLine && <div className="flex-shrink-0 px-4 py-1 text-xs leading-4 text-gray-500">{statusLine}</div>}
      </CompactCard>
      <HearingDigestDialog hearingId={prepId} onClose={() => setPrepId(null)} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

function Markers({ hearing, task, event }: { hearing: number; task: number; event: number }) {
  return (
    <span className="mt-px flex h-1.5 items-center justify-center gap-0.5" aria-hidden="true">
      {hearing > 0 && <i className="block h-[3px] w-3.5 rounded-sm bg-[var(--ci-warn)]" />}
      {event > 0 && <i className="block h-[5px] w-[5px] rounded-full bg-[var(--ci-ink)]" />}
      {task > 0 && <i className="block h-[5px] w-[5px] rotate-45 bg-[var(--ci-seal)]" />}
    </span>
  );
}

export function CompactCalendar({
  caseId,
  hearings,
  caseItem,
  mode,
  items,
  onEditDetails,
}: {
  caseId: number;
  hearings: Hearing[];
  caseItem: Case;
  mode: "month" | "week";
  items: number;
  onEditDetails: () => void;
}) {
  const { data: tasks = [] } = useTasks({ case_id: caseId });
  const { data: events = [] } = useCaseEvents({ case_id: caseId });
  const [eventOpen, setEventOpen] = useState(false);
  const today = istDayKey();

  const buckets = useMemo(() => buildDayBuckets({ hearings, tasks, events }), [hearings, tasks, events]);
  const coming = comingUpRows(buckets, today, items);

  const cell = (day: string, inMonth: boolean, isToday: boolean, big?: boolean) => {
    const counts = dayMarkerCounts(buckets.get(day));
    const n = dayKeyToDate(day).getDate();
    return (
      <div
        key={day}
        title={`${shortDay(day)}${counts.hearing + counts.task + counts.event ? ` — ${counts.hearing} hearing, ${counts.event} event, ${counts.task} deadline` : ""}`}
        className={cn(
          "flex flex-col items-center justify-center border-b border-r border-gray-100 text-[12px]",
          big ? "h-10 rounded border border-gray-200" : "h-[30px]",
          !inMonth && "text-gray-300",
        )}
      >
        <span
          className={cn(
            "flex h-[22px] w-[22px] items-center justify-center rounded-full leading-none",
            isToday ? "bg-[var(--ci-ink)] font-bold text-[color:var(--ci-paper)]" : "text-gray-800",
            big && "h-auto w-auto rounded px-1.5 py-0.5",
          )}
        >
          {big ? `${shortDay(day).split(" ")[0]} ${n}` : n}
        </span>
        <Markers {...counts} />
      </div>
    );
  };

  return (
    <>
      <CompactCard
        id="calendar"
        title="Calendar"
        icon={<CalendarDays className="h-4 w-4" />}
        actions={
          <Button variant="secondary" size="sm" onClick={() => setEventOpen(true)}>
            <Plus className="h-3.5 w-3.5" />
            Event
          </Button>
        }
        dialog={{
          children: (
            <CaseCalendarCard caseId={caseId} hearings={hearings} partyRole={caseItem.user_party_role} onEditDetails={onEditDetails} />
          ),
          footer: "Hearings, events and deadlines for this case",
        }}
      >
        <div className={cn("grid px-4", mode === "month" ? "grid-cols-[minmax(0,252px)_minmax(0,1fr)] gap-5 py-2.5" : "grid-cols-1 gap-1 py-2")}>
          {mode === "month" ? (
            <div role="grid" aria-label="This month" className="min-w-0">
              <div className="grid grid-cols-7 font-mono text-[10px] uppercase tracking-[0.06em] text-gray-500">
                {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
                  <div key={d} className="px-1 pb-0.5 text-center">
                    {d}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7 border-l border-t border-gray-100">
                {miniMonthWeeks(today).flat().map((d) => cell(d.day, d.inMonth, d.isToday))}
              </div>
            </div>
          ) : (
            <div role="grid" aria-label="This week" className="grid grid-cols-7 gap-1.5">
              {weekStrip(today).map((d) => cell(d.day, d.inMonth, d.isToday, true))}
            </div>
          )}
          <div className="min-w-0">
            <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-gray-500">Coming up</div>
            {coming.length === 0 ? (
              <p className="py-2 text-[13px] text-gray-500">Nothing coming up on this case.</p>
            ) : (
              <ul>
                {coming.map((row, i) => (
                  <li key={`${row.day}-${i}`} className={cn("flex items-center gap-3 border-b border-gray-100 last:border-b-0", mode === "month" ? "h-[30px]" : "h-7")}>
                    <span className="w-[72px] flex-shrink-0 font-serif text-[13px] font-bold text-gray-900">{dateLabel(row.day, today) === "Today" || dateLabel(row.day, today) === "Tomorrow" ? dateLabel(row.day, today) : shortDay(row.day)}</span>
                    <span className="min-w-0 truncate text-[13px] text-gray-600">{row.text}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </CompactCard>
      <CaseEventDialog isOpen={eventOpen} onClose={() => setEventOpen(false)} caseId={caseId} event={null} defaultDate={todayKey()} />
    </>
  );
}
