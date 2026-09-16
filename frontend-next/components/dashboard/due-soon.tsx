"use client";

import Link from "next/link";
import { ListChecks } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { formatHearingDate, staggerDelay } from "@/lib/utils";
import { daysUntilDate, dueChipVariant, dueLabel } from "@/lib/tasks";
import type { Task } from "@/types";

interface DueSoonProps {
  /** Open, dated tasks due within the window (overdue included), soonest first. */
  tasks: Task[];
  windowDays: number;
}

/** Tasks and deadlines due soon, across every case -- the dashboard side
 * of the same list each case page shows. */
export function DueSoon({ tasks, windowDays }: DueSoonProps) {
  return (
    <Card className="mb-5">
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="flex items-center gap-2">
          <ListChecks className="h-4 w-4" />
          Due Soon
          {tasks.length > 0 && <span className="ci-chip ci-chip--none">{tasks.length}</span>}
        </CardTitle>
        <span className="text-xs text-gray-400">Overdue and next {windowDays} days</span>
      </CardHeader>
      <CardContent>
        {tasks.length === 0 ? (
          <p className="text-gray-500 text-sm py-2">Nothing due in the next {windowDays} days.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {tasks.map((task, i) => {
              const days = daysUntilDate(task.due_date as string);
              const body = (
                <>
                  <span className={`ci-chip ci-chip--${dueChipVariant(days)} w-28 text-center`}>
                    {dueLabel(days)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-900 truncate">{task.title}</div>
                    <div className="text-xs text-gray-500 truncate">
                      <span className="font-mono">{formatHearingDate(task.due_date)}</span>
                      {task.case_number && ` · ${task.case_number}`}
                      {task.kind !== "manual" && ` · ${task.kind_display}`}
                    </div>
                  </div>
                </>
              );
              return (
                <li
                  key={task.id}
                  style={staggerDelay(i)}
                  className="animate-fade-up motion-reduce:animate-none"
                >
                  {task.case ? (
                    <Link
                      href={`/cases/${task.case}`}
                      className="flex items-center gap-3 py-2.5 px-1 rounded-lg hover:bg-gray-50"
                    >
                      {body}
                    </Link>
                  ) : (
                    <div className="flex items-center gap-3 py-2.5 px-1">{body}</div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
