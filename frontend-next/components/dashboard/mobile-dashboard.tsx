"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { AlertTriangle, CalendarClock, ChevronRight, FileWarning, Gavel, Mail, Receipt } from "lucide-react";
import { RefreshAllButton } from "@/components/dashboard/refresh-all-button";
import { CauseChipView, STATUS_COLOR } from "@/components/dashboard/status";
import { panelId, tabId } from "@/components/dashboard/view-toggle";
import type { BillingState } from "@/components/dashboard/glance-column";
import { AnimatedCheck, MSection, riseIn } from "@/components/mobile/primitives";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardView } from "@/hooks/use-dashboard-view";
import { dateLabel, dayMonth, shortDay } from "@/lib/dashboard/dates";
import {
  STATUS_LABEL,
  STATUS_ORDER,
  causeChip,
  type DashboardModel,
  type NeedItem,
} from "@/lib/dashboard/model";
import { compactINR, dueUrgency, dueWords, relativeDay } from "@/lib/mobile-format";
import { cn, pluralize, staggerDelay } from "@/lib/utils";

interface MobileDashboardProps {
  model: DashboardModel;
  greeting: string;
  billing: BillingState;
  view: DashboardView;
  onViewChange: (view: DashboardView) => void;
  completingTaskId?: number;
  onCompleteTask: (taskId: number) => void;
  /** The Practice map, shown when that view is chosen. */
  map: ReactNode;
}

const NEED_ICON = {
  task: CalendarClock,
  draft: Mail,
  unbilled: Receipt,
  failed_document: FileWarning,
} as const;

/** The dashboard on a phone: what is in court today, what needs you, what is
 * coming -- as cards you can read in a glance and tap, instead of the
 * Briefing's paragraphs. Built from the same DashboardModel the desktop
 * Briefing reads, so the two cannot disagree. */
export function MobileDashboard({
  model,
  greeting,
  billing,
  view,
  onViewChange,
  completingTaskId,
  onCompleteTask,
  map,
}: MobileDashboardProps) {
  const { today } = model;
  // Tasks ticked off on this screen: the row plays its check and folds away
  // while the request is in flight (and stays folded; the list refreshes).
  const [done, setDone] = useState<ReadonlySet<number>>(new Set());

  const needsByCase = useMemo(() => {
    const byCase = new Map<number, NeedItem[]>();
    for (const n of model.needs) {
      if (n.caseId === null) continue;
      byCase.set(n.caseId, [...(byCase.get(n.caseId) ?? []), n]);
    }
    return byCase;
  }, [model.needs]);

  function complete(taskId: number) {
    setDone((current) => new Set(current).add(taskId));
    onCompleteTask(taskId);
  }

  const upcomingDays = model.days.filter((d) => d.count > 0);
  const stats: { id: string; label: string; value: number; tone: "alert" | "pending" | "none" }[] = [
    { id: "m-today", label: "In court today", value: model.todays.length, tone: model.todays.length ? "pending" : "none" },
    {
      id: "m-needs",
      label: "Needs you",
      value: model.needs.length,
      tone: model.needs.some((n) => dueUrgency(n.due, today) === "alert") ? "alert" : model.needs.length ? "pending" : "none",
    },
    { id: "m-next", label: "Next 14 days", value: model.comingUp.total, tone: "none" },
    { id: "m-since", label: "New dates", value: model.since.count, tone: model.since.count ? "pending" : "none" },
  ];

  return (
    <div data-testid="mobile-dashboard" className="px-4 pb-6 pt-4">
      {/* Greeting */}
      <header className="animate-rise-in motion-reduce:animate-none">
        <h1 className="!text-[27px] !font-bold !leading-[1.1] text-gray-900">{greeting}</h1>
        <p className="mt-1 text-[14px] leading-snug text-gray-600">{model.lead}</p>
        <p className="mt-1.5 font-mono text-[11px] uppercase tracking-[0.08em] text-gray-500">
          {model.dateLine} · {pluralize(model.activeCaseCount, "active case")}
        </p>
      </header>

      {/* At-a-glance numbers: tap one to jump to its section */}
      <div className="ci-hscroll -mx-4 mt-4 px-4 pb-1" aria-label="At a glance">
        {stats.map((stat, i) => (
          <button
            key={stat.id}
            type="button"
            onClick={() => {
              onViewChange("brief");
              document.getElementById(stat.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
            }}
            style={staggerDelay(i, 60)}
            className={cn(
              "flex h-[52px] min-w-[104px] animate-settle items-center gap-2.5 rounded-[3px] border bg-surface px-3 text-left motion-reduce:animate-none",
              stat.tone === "alert" && "border-[var(--ci-seal)]",
              stat.tone === "pending" && "border-[var(--ci-warn)]",
              stat.tone === "none" && "border-[var(--ci-ink-14)]",
            )}
          >
            <span
              className={cn(
                "font-serif text-[26px] font-bold leading-none tabular-nums",
                stat.tone === "alert" && "text-[color:var(--ci-seal)]",
                stat.tone === "pending" && "text-[color:var(--ci-warn)]",
                stat.tone === "none" && "text-gray-900",
              )}
            >
              {stat.value}
            </span>
            <span className="text-[11.5px] font-semibold leading-tight text-gray-600">{stat.label}</span>
          </button>
        ))}
      </div>

      {/* Briefing | Practice map, with a sliding marker */}
      <div
        role="tablist"
        aria-label="Dashboard view"
        className="relative mt-4 grid grid-cols-2 rounded-[7px] border border-gray-200 bg-[var(--ci-paper-2)] p-[3px]"
      >
        <span
          aria-hidden="true"
          className="absolute bottom-[3px] left-[3px] top-[3px] w-[calc(50%-3px)] rounded-[5px] bg-surface shadow-[0_1px_2px_rgba(14,26,44,0.14),0_0_0_1px_var(--ci-ink-14)] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] motion-reduce:transition-none"
          style={{ transform: view === "brief" ? "translateX(0)" : "translateX(100%)" }}
        />
        {(
          [
            ["brief", "Briefing"],
            ["map", "Practice map"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            id={tabId(id)}
            type="button"
            role="tab"
            aria-selected={view === id}
            aria-controls={panelId(id)}
            onClick={() => onViewChange(id)}
            className={cn(
              "relative z-10 h-11 rounded-[5px] text-[13.5px] font-semibold transition-colors",
              view === id ? "text-gray-900" : "text-gray-600",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {view === "map" ? (
        <div className="mt-4 animate-rise-in motion-reduce:animate-none">{map}</div>
      ) : (
        <div role="presentation" className="mt-1">
          {/* Today in court */}
          <MSection id="m-today" title="Today in court" count={model.todays.length}>
            {model.todays.length === 0 ? (
              <p className="rounded-[3px] border border-dashed border-gray-200 px-4 py-5 text-center text-[14px] text-gray-500">
                Nothing is in court today.
              </p>
            ) : (
              <ul className="flex flex-col gap-2.5 pb-2">
                {model.todays.map(({ hearing, number }, i) => {
                  const chip = causeChip(hearing);
                  const lastOrder = model.lastOrders.get(hearing.caseId);
                  const caseNeeds = needsByCase.get(hearing.caseId) ?? [];
                  const task = caseNeeds.find((n) => n.kind === "task");
                  return (
                    <li key={hearing.id} style={riseIn(i).style} className={riseIn(i).className}>
                      <Link
                        href={`/cases/${hearing.caseId}`}
                        className="flex gap-3 rounded-[3px] border border-[var(--ci-ink-14)] bg-surface p-3 shadow-card [--press-scale:0.985]"
                      >
                        <div
                          aria-hidden="true"
                          className="flex h-[56px] w-[48px] flex-shrink-0 flex-col items-center justify-center rounded-[3px] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]"
                        >
                          <span className="font-serif text-[23px] font-bold leading-none tabular-nums">{hearing.item || "–"}</span>
                          <span className="mt-0.5 font-mono text-[9px] tracking-[0.14em] opacity-70">ITEM</span>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="line-clamp-2 text-[15px] font-semibold leading-snug text-gray-900">{hearing.caseTitle}</div>
                          <div className="mt-0.5 truncate text-[12.5px] text-gray-600">
                            {[hearing.court || "Court not recorded", hearing.hall && `Hall ${hearing.hall}`].filter(Boolean).join(" · ")}
                          </div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                            <CauseChipView chip={chip} />
                            {number && <span className="font-mono text-[11px] text-gray-500">{number}</span>}
                            {task && (
                              <span className={cn("ci-chip", `ci-chip--${dueUrgency(task.due, today) === "none" ? "none" : dueUrgency(task.due, today)}`)}>
                                {dueWords(task.due, today) || "Task open"}
                              </span>
                            )}
                          </div>
                          {lastOrder && (
                            <p className="mt-2 line-clamp-2 border-t border-dashed border-gray-200 pt-1.5 text-[12.5px] leading-snug text-gray-600">
                              <span className="font-mono text-[10.5px] uppercase tracking-wide text-gray-500">
                                Last order {dayMonth(lastOrder.day)}
                              </span>{" "}
                              {lastOrder.text}
                            </p>
                          )}
                        </div>
                        <ChevronRight aria-hidden="true" className="mt-1 h-4 w-4 flex-shrink-0 text-gray-400" />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </MSection>

          {/* Needs you */}
          <MSection id="m-needs" title="Needs you" count={model.needs.length}>
            {model.needs.length === 0 ? (
              <p className="rounded-[3px] border border-dashed border-gray-200 px-4 py-5 text-center text-[14px] text-gray-500">
                Nothing is waiting on you.
              </p>
            ) : (
              <ul className="overflow-hidden rounded-[3px] border border-[var(--ci-ink-14)] bg-surface shadow-card">
                {model.needs.map((item, i) => (
                  <NeedRow
                    key={item.key}
                    item={item}
                    today={today}
                    index={i}
                    done={item.taskId !== undefined && done.has(item.taskId)}
                    pending={completingTaskId === item.taskId}
                    onComplete={complete}
                  />
                ))}
              </ul>
            )}
          </MSection>

          {/* The next fortnight */}
          <MSection id="m-next" title="Next 14 days" count={model.comingUp.total} defaultOpen>
            {upcomingDays.length === 0 ? (
              <p className="rounded-[3px] border border-dashed border-gray-200 px-4 py-5 text-center text-[14px] text-gray-500">
                No hearings in the next 14 days.
              </p>
            ) : (
              <ul className="overflow-hidden rounded-[3px] border border-[var(--ci-ink-14)] bg-surface shadow-card">
                {upcomingDays.map((d, i) => (
                  <li key={d.day} style={riseIn(i).style} className={cn("border-b border-gray-100 last:border-0", riseIn(i).className)}>
                    <div className="flex items-center gap-2 px-3 pb-1 pt-2.5">
                      <span className="font-serif text-[14.5px] font-bold text-gray-900">{dateLabel(d.day, today)}</span>
                      {dateLabel(d.day, today) === "Today" || dateLabel(d.day, today) === "Tomorrow" ? (
                        <span className="font-mono text-[11px] text-gray-500">{shortDay(d.day)}</span>
                      ) : null}
                      {d.multiCourt && (
                        <span className="ci-chip ci-chip--pending inline-flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                          {d.courts.length} courts
                        </span>
                      )}
                      <span className="ci-chip ci-chip--none ml-auto">{d.count}</span>
                    </div>
                    <ul className="pb-1.5">
                      {d.hearings.map((h) => (
                        <li key={h.id}>
                          <Link
                            href={`/cases/${h.caseId}`}
                            className="flex min-h-[44px] items-center gap-2 px-3 py-1 [--press-scale:0.99]"
                          >
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-[13.5px] font-semibold text-gray-900">{h.caseTitle}</span>
                              <span className="block truncate text-[12px] text-gray-500">{h.court || "Court not recorded"}</span>
                            </span>
                            <CauseChipView chip={causeChip(h)} />
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </MSection>

          {/* eCourts moved a date */}
          <MSection id="m-since" title="Since your last visit" count={model.since.count} defaultOpen={false}>
            {model.since.count === 0 ? (
              <p className="px-1 pb-3 text-[14px] text-gray-600">Nothing has changed since your last visit.</p>
            ) : (
              <div className="pb-2">
                <p className="px-1 pb-2 text-[13.5px] leading-snug text-gray-600">
                  eCourts moved {pluralize(model.since.count, "case")} to a new date
                  {model.since.earliest ? `, the earliest ${relativeDay(model.since.earliest, today).toLowerCase()}` : ""}.
                  {model.since.clash && (
                    <span className="mt-1.5 block rounded-[3px] bg-[var(--ci-warn-soft)] px-2 py-1.5 text-[12.5px] text-[color:var(--ci-warn)]">
                      {shortDay(model.since.clash.day)} now has hearings in {model.since.clash.courts} different courts.
                    </span>
                  )}
                </p>
                <ul className="overflow-hidden rounded-[3px] border border-[var(--ci-ink-14)] bg-surface">
                  {model.changedCases.map((c) => (
                    <li key={c.caseId} className="border-b border-gray-100 last:border-0">
                      <Link href={`/cases/${c.caseId}`} className="flex min-h-[48px] items-center gap-2 px-3 py-1.5 [--press-scale:0.99]">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13.5px] font-semibold text-gray-900">{c.title}</span>
                          <span className="block truncate text-[12px] text-gray-500">{c.number}</span>
                        </span>
                        <span className="ci-chip ci-chip--pending">{shortDay(c.day)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </MSection>

          {/* Practice + billing at a glance */}
          <MSection id="m-practice" title="Your practice" count={model.activeCaseCount} defaultOpen={false}>
            <div className="mb-2 rounded-[3px] border border-[var(--ci-ink-14)] bg-surface p-3">
              <div
                role="img"
                aria-label={STATUS_ORDER.map((s) => `${model.counts[s]} ${STATUS_LABEL[s].toLowerCase()}`).join(", ")}
                className="flex h-3 gap-0.5 overflow-hidden rounded-[3px] bg-[var(--ci-ink-08)]"
              >
                {STATUS_ORDER.map((s) => (
                  <i key={s} className="block min-w-0 rounded-[1px]" style={{ flex: model.counts[s], background: STATUS_COLOR[s] }} />
                ))}
              </div>
              <ul className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12.5px] text-gray-600">
                {STATUS_ORDER.map((s) => (
                  <li key={s} className="flex items-center gap-2">
                    <i aria-hidden="true" className="h-2.5 w-2.5 flex-none rounded-[2px] ring-1 ring-inset ring-[var(--ci-ink-14)]" style={{ background: STATUS_COLOR[s] }} />
                    <span className="truncate">{STATUS_LABEL[s]}</span>
                    <b className="ml-auto tabular-nums text-gray-900">{model.counts[s]}</b>
                  </li>
                ))}
              </ul>
            </div>
          </MSection>

          <BillingStrip billing={billing} />

          <div className="mt-4 flex items-center gap-2 text-[12px] text-gray-500">
            <Gavel className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
            <RefreshAllButton compact />
          </div>
        </div>
      )}
    </div>
  );
}

/** One task, check, or item to review. A task has a round check on the left:
 * tap it and the check pops, the row folds away. Anything else is a link to
 * where it is dealt with. */
function NeedRow({
  item,
  today,
  index,
  done,
  pending,
  onComplete,
}: {
  item: NeedItem;
  today: string;
  index: number;
  done: boolean;
  pending: boolean;
  onComplete: (taskId: number) => void;
}) {
  const urgency = dueUrgency(item.due, today);
  const Icon = NEED_ICON[item.kind];
  const target =
    item.kind === "draft" ? "/messages" : item.kind === "unbilled" ? "/billing" : item.caseId ? `/cases/${item.caseId}` : "/documents";
  const text = item.text.charAt(0).toUpperCase() + item.text.slice(1);
  const words = dueWords(item.due, today);

  const body = (
    <>
      <span className="block text-[14px] font-semibold leading-snug text-gray-900">{text}</span>
      <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-gray-500">
        {item.caseTitle && <span className="min-w-0 max-w-full truncate">{item.caseTitle}</span>}
        {words && <span className={cn("ci-chip", `ci-chip--${urgency}`)}>{words}</span>}
      </span>
    </>
  );

  return (
    <li
      style={staggerDelay(index, 45, 12)}
      className={cn(
        "grid animate-rise-in border-b border-gray-100 transition-[grid-template-rows,opacity] duration-300 ease-out last:border-0 motion-reduce:animate-none motion-reduce:transition-none",
        done ? "grid-rows-[0fr] opacity-0 delay-500" : "grid-rows-[1fr] opacity-100",
      )}
    >
      <div className="min-h-0 overflow-hidden">
        <div className="flex min-h-[60px] items-center gap-1 pl-1 pr-2">
          {item.kind === "task" && item.taskId !== undefined ? (
            <button
              type="button"
              disabled={pending || done}
              aria-label={`Mark done: ${item.text}`}
              onClick={() => onComplete(item.taskId!)}
              className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full [--press-scale:0.85]"
            >
              {done ? (
                <AnimatedCheck />
              ) : (
                <span className={cn("h-6 w-6 rounded-full border-2", urgency === "alert" ? "border-[var(--ci-seal)]" : "border-[var(--ci-ink-45)]")} />
              )}
            </button>
          ) : (
            <span aria-hidden="true" className="flex h-11 w-11 flex-shrink-0 items-center justify-center text-gray-500">
              <Icon className="h-5 w-5" strokeWidth={1.7} />
            </span>
          )}
          {item.kind === "task" ? (
            <Link href={item.caseId ? `/cases/${item.caseId}` : "/dashboard"} className="min-w-0 flex-1 py-2 [--press-scale:0.99]">
              {body}
            </Link>
          ) : (
            <Link href={target} className="flex min-w-0 flex-1 items-center gap-1 py-2 [--press-scale:0.99]">
              <span className="min-w-0 flex-1">{body}</span>
              <ChevronRight aria-hidden="true" className="h-4 w-4 flex-shrink-0 text-gray-400" />
            </Link>
          )}
        </div>
      </div>
    </li>
  );
}

function BillingStrip({ billing }: { billing: BillingState }) {
  const { data } = billing;
  if (billing.isLoading) return <Skeleton className="mt-3 h-[72px] w-full rounded-[3px]" />;
  if (billing.error || !data) return null;
  const old = data.aging.filter((b) => b.label !== "0-30").reduce((n, b) => n + b.count, 0);
  const cells: [string, string][] = [
    ["Outstanding", `₹${compactINR(data.totals.invoiced_amount)}`],
    ["Unbilled", String(data.uninvoiced_hearings_total)],
    ["Over 30 days", String(old)],
  ];
  return (
    <Link
      href="/billing"
      aria-label="Billing: open"
      className="mt-3 block animate-rise-in rounded-[3px] border border-[var(--ci-ink-14)] bg-surface p-3 shadow-card [--press-scale:0.985] motion-reduce:animate-none"
    >
      <div className="mb-2 flex items-center gap-2">
        <Receipt className="h-4 w-4 text-gray-600" aria-hidden="true" />
        <span className="font-serif text-[15px] font-bold text-gray-900">Billing</span>
        <span className="ml-auto flex items-center gap-0.5 text-[12.5px] font-semibold text-gray-700">
          Open <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        </span>
      </div>
      <dl className="grid grid-cols-3 gap-2">
        {cells.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="truncate font-mono text-[10px] uppercase tracking-[0.08em] text-gray-500">{label}</dt>
            <dd className="mt-0.5 truncate text-[15px] font-bold tabular-nums text-gray-900">{value}</dd>
          </div>
        ))}
      </dl>
    </Link>
  );
}
