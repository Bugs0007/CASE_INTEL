import { apiClient } from "./client";
import type { Task, TaskFilters, TaskInput } from "@/types";

export const tasksApi = {
  list: (filters: TaskFilters = {}) =>
    apiClient<Task[]>("/tasks/", { params: { ...filters } }),

  create: (data: TaskInput) =>
    apiClient<Task>("/tasks/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (id: number, data: Partial<TaskInput>) =>
    apiClient<Task>(`/tasks/${id}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  /** Manual tasks only -- the API refuses to delete a system-generated
   * task (dismiss it with status "cancelled" instead). */
  delete: (id: number) => apiClient<void>(`/tasks/${id}/`, { method: "DELETE" }),
};
