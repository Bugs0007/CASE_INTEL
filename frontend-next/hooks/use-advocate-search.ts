import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { advocateSearchApi } from "@/lib/api/advocate-search";
import { caseKeys } from "@/hooks/use-cases";
import type { AdvocateImportSelection, AdvocateSearchRequest, CourtType } from "@/types";

// While an import job is still queued/running, poll so the "N of M added"
// progress stays live -- same convention as useDocument's active-poll.
const ACTIVE_POLL_MS = 1500;

export const advocateSearchKeys = {
  preference: ["advocate-search", "preference"] as const,
  importJob: (jobId: number) => ["advocate-search", "import", jobId] as const,
};

/** Last-used court hierarchy, to pre-fill the search page on load. */
export function useAdvocateSearchPreference() {
  return useQuery({
    queryKey: advocateSearchKeys.preference,
    queryFn: () => advocateSearchApi.getPreference(),
    staleTime: 60 * 1000,
  });
}

/** One synchronous, CAPTCHA-gated portal call -- no polling needed. */
export function useAdvocateSearch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: AdvocateSearchRequest) => advocateSearchApi.search(body),
    onSuccess: () => {
      // The search itself upserts the server-side preference.
      queryClient.invalidateQueries({ queryKey: advocateSearchKeys.preference });
    },
  });
}

export function useImportAdvocateCases() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      courtType,
      selected,
    }: {
      courtType: CourtType;
      selected: AdvocateImportSelection[];
    }) => advocateSearchApi.startImport(courtType, selected),
  });
}

/** Polls an import job until it reaches a terminal state ("succeeded" or
 * "failed"). Callers should invalidate caseKeys.lists() themselves once
 * status is "succeeded" (see the search page) -- new Case rows were
 * created server-side and aren't reflected in the existing case-list
 * cache otherwise. */
export function useAdvocateImportJob(jobId: number | null) {
  return useQuery({
    queryKey: advocateSearchKeys.importJob(jobId ?? -1),
    queryFn: () => advocateSearchApi.getImportStatus(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data || data.status === "succeeded" || data.status === "failed") {
        return false;
      }
      return ACTIVE_POLL_MS;
    },
    refetchOnWindowFocus: false,
  });
}
