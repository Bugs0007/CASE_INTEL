import { useQuery } from "@tanstack/react-query";
import { dailyStatusApi } from "@/lib/api/daily-status";

export const dailyStatusKeys = {
  all: ["daily-status"] as const,
  list: (caseId: number) => [...dailyStatusKeys.all, caseId] as const,
};

/** A district case's daily status (Business on Date) entries, newest first.
 *
 * Entries only arrive with a court-tracking refresh (rate-limited to about
 * hourly) and never change once stored, so there is no need to re-fetch
 * eagerly. `enabled` is false for cases that are not district cases, which
 * have no daily status to ask for. */
export function useDailyStatus(caseId: number, enabled: boolean = true) {
  return useQuery({
    queryKey: dailyStatusKeys.list(caseId),
    queryFn: () => dailyStatusApi.listForCase(caseId),
    enabled: !!caseId && enabled,
    staleTime: 5 * 60 * 1000,
  });
}
