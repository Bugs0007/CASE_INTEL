"use client";

import Link from "next/link";
import { Plus } from "lucide-react";
import { CauseChipView, StatusChip } from "@/components/dashboard/status";
import { dayMonth, shortDay } from "@/lib/dashboard/dates";
import { causeChip, type DashboardModel, type PracticeCase } from "@/lib/dashboard/model";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-dashed border-gray-200 py-1.5 text-[13px] last:border-0">
      <dt className="text-gray-600">{label}</dt>
      <dd className="text-right font-semibold text-gray-900">{children}</dd>
    </div>
  );
}

/** One case at a glance: where it stands, the last order, the next hearing
 * and what is open -- the right-hand panel of the Practice map, or a dialog
 * when the panel does not fit. */
export function CasePeek({
  item,
  model,
  onAddTask,
}: {
  item: PracticeCase;
  model: DashboardModel;
  onAddTask: (caseId: number) => void;
}) {
  const lastOrder = model.lastOrders.get(item.id);
  const chip = item.nextHearing ? causeChip(item.nextHearing) : null;
  const openTasks = model.openTaskCount.get(item.id) ?? 0;

  return (
    <div className="flex flex-col gap-3.5">
      <header>
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <StatusChip status={item.status} />
          <span className="font-mono text-[13px] tracking-[0.04em] text-gray-600">{item.number}</span>
        </div>
        <h3 className="font-serif text-[22px] font-bold leading-tight text-gray-900">{item.title}</h3>
        <p className="mt-1 text-[13px] text-gray-600">{item.court}</p>
      </header>

      <section className="border-t border-gray-100 pt-3">
        <h4 className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.1em] text-gray-500">Latest order</h4>
        {lastOrder ? (
          <p className="text-[13.5px] leading-relaxed text-gray-900">
            <span className="text-gray-500">{dayMonth(lastOrder.day)}: </span>
            {lastOrder.text}
          </p>
        ) : (
          <p className="text-[13.5px] text-gray-500">No order summary yet.</p>
        )}
      </section>

      <dl className="border-t border-gray-100 pt-2">
        <Row label="Next hearing">{item.nextDay ? shortDay(item.nextDay) : "None scheduled"}</Row>
        <Row label="Cause list">
          {item.nextHearing ? (
            (chip && <CauseChipView chip={chip} />) || <span className="font-normal text-gray-500">Not checked yet</span>
          ) : (
            <span className="font-normal text-gray-500">—</span>
          )}
        </Row>
        <Row label="Open tasks">{openTasks}</Row>
      </dl>

      <div className="mt-1 flex gap-2">
        <Link
          href={`/cases/${item.id}`}
          className="inline-flex h-10 items-center justify-center rounded border border-[var(--ci-ink)] bg-[var(--ci-ink)] px-4 text-sm font-semibold text-[color:var(--ci-paper)] hover:border-[var(--ci-seal)] hover:bg-[var(--ci-seal)]"
        >
          Open case
        </Link>
        <button
          type="button"
          onClick={() => onAddTask(item.id)}
          className="inline-flex h-10 items-center justify-center gap-1.5 rounded border border-[var(--ci-ink-14)] bg-surface px-4 text-sm font-semibold text-gray-900 hover:border-[var(--ci-ink)]"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2} />
          Add task
        </button>
      </div>
    </div>
  );
}
