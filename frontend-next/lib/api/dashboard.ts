import { apiClient } from "./client";
import type { DashboardData, UpcomingHearing } from "@/types";

export const dashboardApi = {
  get: () => apiClient<DashboardData>("/dashboard/"),
  upcomingHearings: () =>
    apiClient<UpcomingHearing[]>("/dashboard/upcoming-hearings/"),
};
