import { apiClient } from "./client";
import type { DashboardData } from "@/types";

export const dashboardApi = {
  get: () => apiClient<DashboardData>("/dashboard/"),
};
