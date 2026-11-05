"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showToast } from "@/components/ui/toaster";
import { useModalLayer } from "@/hooks/use-modal-layer";
import { useCreateTask } from "@/hooks/use-tasks";

/** Adds a task to a case from the dashboard. Same call the Tasks card on the
 * case page makes (useCreateTask), which refreshes every task list. */
export function AddTaskDialog({
  caseId,
  caseTitle,
  onClose,
}: {
  caseId: number | null;
  caseTitle: string;
  onClose: () => void;
}) {
  const isOpen = caseId !== null;
  const panelRef = useRef<HTMLDivElement>(null);
  const [title, setTitle] = useState("");
  const [dueDate, setDueDate] = useState("");
  const createTask = useCreateTask();
  useModalLayer(panelRef, isOpen);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || caseId === null) return;
    try {
      await createTask.mutateAsync({ case: caseId, title: trimmed, due_date: dueDate || null });
      showToast.success("Task added", caseTitle);
      setTitle("");
      setDueDate("");
      onClose();
    } catch (error) {
      console.error("Failed to add task:", error);
      showToast.error("Could not add task", "Try again in a moment.");
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onMouseDown={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Add task"
        className="relative w-full max-w-md rounded-lg border border-gray-200 bg-surface p-5 shadow-card"
      >
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-gray-900">Add task</h2>
            <p className="truncate text-xs text-gray-500">{caseTitle}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close add task"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            autoFocus
            aria-label="Task"
            placeholder="e.g. Collect certified copy of the order"
            value={title}
            maxLength={255}
            onChange={(e) => setTitle(e.target.value)}
          />
          <Input type="date" aria-label="Due date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!title.trim() || createTask.isPending}>
              Add task
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
