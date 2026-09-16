"use client";

import { useState, type FormEvent } from "react";
import { CheckCircle2, Circle, ListChecks, Plus, RotateCcw, Scale, Trash2, X } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showToast } from "@/components/ui/toaster";
import { LimitationDeadlineForm } from "@/components/tasks/limitation-deadline-form";
import { useCreateTask, useDeleteTask, useTasks, useUpdateTask } from "@/hooks/use-tasks";
import { formatHearingDate } from "@/lib/utils";
import {
  DUE_DATE_BASIS_NOTE,
  daysUntilDate,
  dueChipVariant,
  dueLabel,
  isOpenTask,
} from "@/lib/tasks";
import type { CourtType, Task, TaskInput } from "@/types";

interface TasksCardProps {
  caseId: number;
  /** Narrows the limitation rules offered. */
  courtType: CourtType | null;
  /** The case's most recent dated order -- the default start date for a
   * limitation deadline. */
  latestOrder: { id: number; order_date: string } | null;
}

/** Everything due on this case: the advocate's own tasks, directions from
 * court orders, and limitation deadlines -- one list, soonest first.
 *
 * Always rendered (unlike the fee card), because it is also where a
 * manual task is added. */
export function TasksCard({ caseId, courtType, latestOrder }: TasksCardProps) {
  const { data: tasks = [], isLoading } = useTasks({ case_id: caseId });
  const createTask = useCreateTask();
  const updateTask = useUpdateTask();
  const deleteTask = useDeleteTask();

  const [isAdding, setIsAdding] = useState(false);
  const [isAddingLimitation, setIsAddingLimitation] = useState(false);
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [showClosed, setShowClosed] = useState(false);

  const openTasks = tasks.filter(isOpenTask);
  const closedTasks = tasks.filter((task) => !isOpenTask(task));

  const busyId =
    (updateTask.isPending ? updateTask.variables?.id : undefined) ??
    (deleteTask.isPending ? deleteTask.variables : undefined);

  async function handleAdd(e: FormEvent) {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    try {
      await createTask.mutateAsync({ case: caseId, title: trimmed, due_date: dueDate || null });
      setTitle("");
      setDueDate("");
      setIsAdding(false);
    } catch (error) {
      console.error("Failed to add task:", error);
      showToast.error("Could not add task", "Try again in a moment.");
    }
  }

  function update(task: Task, data: Partial<TaskInput>) {
    updateTask.mutate(
      { id: task.id, data },
      {
        onError: (error) => {
          console.error("Failed to update task:", error);
          showToast.error("Could not update task", "Try again in a moment.");
        },
      },
    );
  }

  function remove(task: Task) {
    if (task.kind !== "manual") {
      // Generated tasks are dismissed, never deleted -- a deleted one
      // would come back the next time its order is processed.
      update(task, { status: "cancelled" });
      return;
    }
    if (!confirm("Delete this task?")) return;
    deleteTask.mutate(task.id, {
      onError: (error) => {
        console.error("Failed to delete task:", error);
        showToast.error("Could not delete task", "Try again in a moment.");
      },
    });
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="flex items-center gap-2">
          <ListChecks className="h-4 w-4" />
          Tasks &amp; Deadlines
          {openTasks.length > 0 && (
            <span className="ci-chip ci-chip--none">{openTasks.length} open</span>
          )}
        </CardTitle>
        {!isAdding && !isAddingLimitation && (
          <div className="flex gap-2">
            <Button variant="secondary" size="sm" onClick={() => setIsAddingLimitation(true)}>
              <Scale className="h-4 w-4 mr-1" />
              Limitation
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setIsAdding(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Add task
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {isAddingLimitation && (
          <LimitationDeadlineForm
            caseId={caseId}
            courtType={courtType}
            latestOrder={latestOrder}
            onDone={() => setIsAddingLimitation(false)}
          />
        )}

        {isAdding && (
          <form onSubmit={handleAdd} className="flex flex-col @md:flex-row gap-2">
            <Input
              autoFocus
              aria-label="Task"
              placeholder="e.g. Collect certified copy of the order"
              value={title}
              maxLength={255}
              onChange={(e) => setTitle(e.target.value)}
              className="@md:flex-1"
            />
            <Input
              type="date"
              aria-label="Due date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="@md:w-44"
            />
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={!title.trim() || createTask.isPending}>
                Add
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setIsAdding(false);
                  setTitle("");
                  setDueDate("");
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        )}

        {isLoading ? (
          <p className="text-sm text-gray-400 py-2">Loading tasks…</p>
        ) : openTasks.length === 0 ? (
          !isAdding && (
            <p className="text-sm text-gray-500 py-2">Nothing due on this case.</p>
          )
        ) : (
          <ul className="divide-y divide-gray-100">
            {openTasks.map((task) => (
              <TaskRow
                key={task.id}
                task={task}
                busy={busyId === task.id}
                onToggle={() => update(task, { status: "completed" })}
                onConfirm={() => update(task, { needs_review: false })}
                onRemove={() => remove(task)}
              />
            ))}
          </ul>
        )}

        {closedTasks.length > 0 && (
          <div>
            <button
              type="button"
              onClick={() => setShowClosed((v) => !v)}
              className="text-xs text-gray-500 hover:text-gray-900"
            >
              {showClosed ? "Hide" : "Show"} {closedTasks.length} completed or dismissed
            </button>
            {showClosed && (
              <ul className="mt-2 divide-y divide-gray-100">
                {closedTasks.map((task) => (
                  <li key={task.id} className="flex items-center gap-3 py-2">
                    <CheckCircle2 className="h-4 w-4 text-gray-300 flex-shrink-0" />
                    <span className="flex-1 min-w-0 text-sm text-gray-400 line-through truncate">
                      {task.title}
                    </span>
                    <span className="text-xs text-gray-400">
                      {task.status === "cancelled" ? "Dismissed" : "Done"}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busyId === task.id}
                      onClick={() => update(task, { status: "pending" })}
                      aria-label={`Reopen ${task.title}`}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface TaskRowProps {
  task: Task;
  busy: boolean;
  onToggle: () => void;
  onConfirm: () => void;
  onRemove: () => void;
}

function TaskRow({ task, busy, onToggle, onConfirm, onRemove }: TaskRowProps) {
  const days = task.due_date ? daysUntilDate(task.due_date) : null;
  const basisNote = DUE_DATE_BASIS_NOTE[task.due_date_basis];
  const isGenerated = task.kind !== "manual";

  return (
    <li className="flex items-start gap-3 py-3">
      <button
        type="button"
        onClick={onToggle}
        disabled={busy}
        aria-label={`Mark "${task.title}" done`}
        className="mt-0.5 text-gray-400 hover:text-status-ok disabled:opacity-50 flex-shrink-0"
      >
        <Circle className="h-4 w-4" />
      </button>

      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-900">{task.title}</span>
          {isGenerated && <span className="ci-chip ci-chip--none">{task.kind_display}</span>}
          {task.needs_review && <span className="ci-chip ci-chip--pending">Suggested</span>}
        </div>

        {task.source_text && task.source_text !== task.title && (
          <p className="text-xs text-gray-500 italic">“{task.source_text}”</p>
        )}

        {task.description && <p className="text-xs text-gray-500">{task.description}</p>}

        {task.due_date && days !== null && (
          <div className="flex items-center gap-2 flex-wrap text-xs text-gray-500">
            <span className={`ci-chip ci-chip--${dueChipVariant(days)}`}>{dueLabel(days)}</span>
            <span className="font-mono">{formatHearingDate(task.due_date)}</span>
            {basisNote && <span>· {basisNote}</span>}
          </div>
        )}
      </div>

      <div className="flex items-center gap-1 flex-shrink-0">
        {task.needs_review && (
          <Button variant="secondary" size="sm" disabled={busy} onClick={onConfirm}>
            Confirm
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={onRemove}
          aria-label={isGenerated ? `Dismiss "${task.title}"` : `Delete "${task.title}"`}
          title={isGenerated ? "Dismiss" : "Delete"}
        >
          {isGenerated ? <X className="h-3.5 w-3.5" /> : <Trash2 className="h-3.5 w-3.5" />}
        </Button>
      </div>
    </li>
  );
}
