import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api/dashboard";

export const dashboardKeys = {
  all: ["dashboard"] as const,
  data: () => [...dashboardKeys.all, "data"] as const,
  upcomingHearings: () => [...dashboardKeys.all, "upcoming-hearings"] as const,
};

export function useDashboard() {
  return useQuery({
    queryKey: dashboardKeys.data(),
    queryFn: dashboardApi.get,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useUpcomingHearings() {
  return useQuery({
    queryKey: dashboardKeys.upcomingHearings(),
    queryFn: dashboardApi.upcomingHearings,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
