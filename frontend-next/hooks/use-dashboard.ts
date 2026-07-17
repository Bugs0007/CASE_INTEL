import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api/dashboard";

export const dashboardKeys = {
  all: ["dashboard"] as const,
  data: () => [...dashboardKeys.all, "data"] as const,
  upcomingHearings: (since?: string) =>
    [...dashboardKeys.all, "upcoming-hearings", since] as const,
};

export function useDashboard() {
  return useQuery({
    queryKey: dashboardKeys.data(),
    queryFn: dashboardApi.get,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useUpcomingHearings(since?: string) {
  return useQuery({
    queryKey: dashboardKeys.upcomingHearings(since),
    queryFn: () => dashboardApi.upcomingHearings(since),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
