"use client";

import { showToast } from "@/components/ui/toaster";
import { useViewOrder } from "@/hooks/use-court-orders";
import { useDeleteTask, useUpdateTask } from "@/hooks/use-tasks";
import type { Task, TaskInput } from "@/types";

/** What a task on the calendar can do: the same mutations TasksCard uses
 * (useUpdateTask / useDeleteTask, which invalidate every task list), so the
 * calendar and the Tasks card can never disagree. */
export function useTaskActions() {
  const updateTask = useUpdateTask();
  const deleteTask = useDeleteTask();
  const viewOrder = useViewOrder();

  const busyId =
    (updateTask.isPending ? updateTask.variables?.id : undefined) ??
    (deleteTask.isPending ? deleteTask.variables : undefined);

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

  return {
    busyId,
    viewingOrderId: viewOrder.isPending ? viewOrder.variables : undefined,
    complete: (task: Task) => update(task, { status: "completed" }),
    reopen: (task: Task) => update(task, { status: "pending" }),
    confirm: (task: Task) => update(task, { needs_review: false }),
    /** A generated task is dismissed, never deleted -- a deleted one would
     * come back the next time its order is processed. A manual one is
     * deleted. */
    remove: (task: Task) => {
      if (task.kind !== "manual") {
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
    },
    viewOrder: (orderId: number) =>
      viewOrder.mutate(orderId, {
        onError: (error) => {
          console.error("Failed to open order:", error);
          showToast.error("Could not open order", "Try again in a moment.");
        },
      }),
  };
}

export type TaskActions = ReturnType<typeof useTaskActions>;
