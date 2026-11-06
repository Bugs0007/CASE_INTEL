import { apiClient } from "./client";
import type { DailyStatusEntry } from "@/types/daily-status";

export const dailyStatusApi = {
  /** The case's stored District Courts daily status entries, newest first.
   * Read-only: the worker fills them after a tracking refresh. */
  listForCase: (caseId: number) =>
    apiClient<DailyStatusEntry[]>(`/cases/${caseId}/daily-status/`),
};
