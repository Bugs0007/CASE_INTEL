"use client";

import Link from "next/link";
import { CheckCircle2, Circle, ExternalLink, Loader2, Pencil, RotateCcw, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CauseListBadge } from "@/components/hearings/cause-list-badge";
import { OrderSummaryBody } from "@/components/cases/order-overview";
import type { TaskActions } from "@/components/calendar/use-task-actions";
import { formatEventTimes, type CalendarItem } from "@/lib/calendar";
import { daysUntilDate, dueChipVariant, dueLabel, isOpenTask } from "@/lib/tasks";
import { cn } from "@/lib/utils";
import type { CaseEvent, Hearing, Task } from "@/types";

interface HearingDayCardProps {
  hearing: Hearing;
  /** The global calendar names the case, links to it and shows its document
   * count; on a case's own page that is all redundant. */
  showCase?: boolean;
  documentCount?: number;
}

/** A hearing in a day's list. The markup the global calendar has always used
 * for its selected-day panel, lifted out unchanged. */
export function HearingDayCard({ hearing: h, showCase = true, documentCount }: HearingDayCardProps) {
  return (
    <div className="border border-gray-100 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        {/* No per-hearing time shown -- eCourts only ever gives a
            DATE, and this panel is already scoped to the single
            selected day, so there's nothing left to add here beyond the
            badges. */}
        <span className="ci-chip ci-chip--none">{h.source === "ecourts" ? "eCourts" : "Manual"}</span>
        <CauseListBadge hearing={h} />
      </div>
      {showCase && <div className="text-sm font-semibold text-gray-900 mb-0.5">{h.case_title}</div>}
      <div className={cn("text-xs text-gray-500", showCase ? "mb-2.5" : "mb-1")}>
        {h.location || "No location specified"}
      </div>
      {!showCase && h.purpose && <div className="text-xs text-gray-700 mb-2.5">{h.purpose}</div>}
      {/* What the court actually did on this date, when an order was
          filed and summarised. */}
      {h.order_summary && (
        <div className="mb-2.5 rounded-lg border border-gray-100 bg-gray-50/60 p-2.5">
          <OrderSummaryBody summary={h.order_summary} />
        </div>
      )}
      {showCase && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">
            {documentCount !== undefined ? `${documentCount} docs on file` : ""}
          </span>
          <Link href={`/cases/${h.case}`}>
            <Button variant="secondary" size="sm">
              View Case
            </Button>
          </Link>
        </div>
      )}
    </div>
  );
}

interface TaskDayCardProps {
  task: Task;
  actions: TaskActions;
  showCase?: boolean;
}

/** A task or order deadline on its due day. An order direction says how its
 * date was arrived at and, until the advocate confirms it, looks provisional
 * (dashed outline) so a counted date never reads as certain as a stated one. */
export function TaskDayCard({ task, actions, showCase = true }: TaskDayCardProps) {
  const open = isOpenTask(task);
  const busy = actions.busyId === task.id;
  const days = task.due_date ? daysUntilDate(task.due_date) : null;
  const isGenerated = task.kind !== "manual";

  return (
    <div
      className={cn(
        "rounded-lg p-3 border",
        task.needs_review ? "border-dashed border-gray-300" : "border-gray-100",
        !open && "opacity-60",
      )}
    >
      <div className="flex items-start gap-2.5">
        <button
          type="button"
          disabled={busy}
          onClick={() => (open ? actions.complete(task) : actions.reopen(task))}
          aria-label={open ? `Mark "${task.title}" done` : `Reopen "${task.title}"`}
          className="mt-0.5 text-gray-400 hover:text-status-ok disabled:opacity-50 flex-shrink-0"
        >
          {open ? <Circle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
        </button>

        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={cn("text-sm font-semibold text-gray-900", !open && "line-through")}>
              {task.title}
            </span>
            {isGenerated && <span className="ci-chip ci-chip--none">{task.kind_display}</span>}
            {task.needs_review && <span className="ci-chip ci-chip--pending">Suggested</span>}
          </div>

          {showCase && task.case_title && (
            <div className="text-xs text-gray-500">{task.case_title}</div>
          )}

          {task.due_date_basis && task.due_date_basis_display && (
            <div className="text-xs text-gray-500">{task.due_date_basis_display}</div>
          )}

          {task.source_text && task.source_text !== task.title && (
            <p className="text-xs text-gray-500 italic">“{task.source_text}”</p>
          )}
          {task.description && <p className="text-xs text-gray-500">{task.description}</p>}

          {open && days !== null && (
            <span className={`ci-chip ci-chip--${dueChipVariant(days)}`}>{dueLabel(days)}</span>
          )}
        </div>
      </div>

      <div className="mt-2 flex items-center justify-end gap-1 flex-wrap">
        {task.source_order && (
          <Button
            variant="secondary"
            size="sm"
            disabled={actions.viewingOrderId === task.source_order}
            onClick={() => actions.viewOrder(task.source_order as number)}
          >
            {actions.viewingOrderId === task.source_order ? (
              <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
            ) : (
              <ExternalLink className="h-3.5 w-3.5 mr-1" />
            )}
            View order
          </Button>
        )}
        {task.needs_review && (
          <Button variant="secondary" size="sm" disabled={busy} onClick={() => actions.confirm(task)}>
            Confirm
          </Button>
        )}
        {open && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => actions.remove(task)}
            aria-label={isGenerated ? `Dismiss "${task.title}"` : `Delete "${task.title}"`}
            title={isGenerated ? "Dismiss" : "Delete"}
          >
            {isGenerated ? <X className="h-3.5 w-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}
          </Button>
        )}
        {!open && (
          <Button
            variant="ghost"
            size="sm"
            disabled={busy}
            onClick={() => actions.reopen(task)}
            aria-label={`Reopen ${task.title}`}
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>
    </div>
  );
}

interface EventDayCardProps {
  event: CaseEvent;
  showCase?: boolean;
  /** Present -> an Edit button. The global calendar links to the case instead. */
  onEdit?: (event: CaseEvent) => void;
}

export function EventDayCard({ event, onEdit, showCase = true }: EventDayCardProps) {
  const inactive = event.status !== "scheduled";
  return (
    <div className={cn("border border-gray-100 rounded-lg p-3", inactive && "opacity-60")}>
      <div className="flex items-center gap-2 mb-1.5 flex-wrap">
        <span className="ci-chip ci-chip--none">{event.event_type_display}</span>
        <span className="text-xs font-mono text-gray-700">
          {formatEventTimes(event.start_time, event.end_time)}
        </span>
        {inactive && (
          <span className={`ci-chip ci-chip--${event.status === "completed" ? "ok" : "none"}`}>
            {event.status === "completed" ? "Done" : "Cancelled"}
          </span>
        )}
      </div>
      <div
        className={cn(
          "text-sm font-semibold text-gray-900",
          event.status === "cancelled" && "line-through",
        )}
      >
        {event.title}
      </div>
      {showCase && <div className="text-xs text-gray-500 mt-0.5">{event.case_title}</div>}
      {event.location && <div className="text-xs text-gray-500 mt-0.5 break-words">{event.location}</div>}
      {event.notes && <p className="text-xs text-gray-600 mt-1.5 whitespace-pre-line">{event.notes}</p>}
      <div className="mt-2 flex justify-end">
        {onEdit ? (
          <Button variant="secondary" size="sm" onClick={() => onEdit(event)}>
            <Pencil className="h-3.5 w-3.5 mr-1" />
            Edit
          </Button>
        ) : (
          <Link href={`/cases/${event.case}`}>
            <Button variant="secondary" size="sm">
              View Case
            </Button>
          </Link>
        )}
      </div>
    </div>
  );
}

interface DayItemsProps {
  items: readonly CalendarItem[];
  taskActions: TaskActions;
  showCase?: boolean;
  caseMeta?: Map<number, { caseNumber: string; documentCount: number }>;
  onEditEvent?: (event: CaseEvent) => void;
}

/** One day's items in display order, each in its own card. */
export function DayItems({ items, taskActions, showCase = true, caseMeta, onEditEvent }: DayItemsProps) {
  return (
    <>
      {items.map((item) => {
        if (item.kind === "hearing") {
          return (
            <HearingDayCard
              key={item.key}
              hearing={item.hearing}
              showCase={showCase}
              documentCount={caseMeta?.get(item.hearing.case)?.documentCount}
            />
          );
        }
        if (item.kind === "event") {
          return (
            <EventDayCard key={item.key} event={item.event} showCase={showCase} onEdit={onEditEvent} />
          );
        }
        return <TaskDayCard key={item.key} task={item.task} actions={taskActions} showCase={showCase} />;
      })}
    </>
  );
}
