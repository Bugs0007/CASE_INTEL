import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { advocateSearchApi } from "@/lib/api/advocate-search";
import { caseKeys } from "@/hooks/use-cases";
import type { AdvocateImportSelection, AdvocateSearchRequest, CourtType } from "@/types";

// While an import job is still queued/running, poll so the "N of M added"
// progress stays live -- same convention as useDocument's active-poll.
const ACTIVE_POLL_MS = 1500;
// A state-wide search is district-granular and runs for minutes, and each
// status response makes the server load the job's whole accumulated result
// payload -- so it is polled less eagerly than the import's "N of M" counter.
const SEARCH_POLL_MS = 3000;

/** Every state a job can end in. A poll must stop on ALL of them: stopping
 * only on succeeded/failed left a cancelled search polling forever. */
const TERMINAL_JOB_STATUSES = ["succeeded", "failed", "cancelled"];

/** refetchInterval for a job-status query: keep going while the job is
 * queued/running, stop at any terminal state. No data yet (first fetch still
 * in flight, or it failed) is also "stop": react-query re-evaluates this after
 * every successful fetch, and a failed first fetch (say a 404) must not turn
 * into an endless poll. */
export function jobPollInterval(
  data: { status: string } | undefined,
  intervalMs: number,
): number | false {
  if (!data || TERMINAL_JOB_STATUSES.includes(data.status)) return false;
  return intervalMs;
}

export const advocateSearchKeys = {
  preference: ["advocate-search", "preference"] as const,
  searchJob: (jobId: number) => ["advocate-search", "search", jobId] as const,
  importJob: (jobId: number) => ["advocate-search", "import", jobId] as const,
};

/** Last-used state, to pre-fill the search page on load. */
export function useAdvocateSearchPreference() {
  return useQuery({
    queryKey: advocateSearchKeys.preference,
    queryFn: () => advocateSearchApi.getPreference(),
    staleTime: 60 * 1000,
  });
}

/** Starts the async state-wide search; returns { job_id } to poll with
 * useAdvocateSearchJob. */
export function useAdvocateSearch() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (body: AdvocateSearchRequest) => advocateSearchApi.search(body),
    onSuccess: () => {
      // The search enqueue also upserts the server-side state preference.
      queryClient.invalidateQueries({ queryKey: advocateSearchKeys.preference });
    },
  });
}

/** Polls a state-wide search job until it reaches a terminal state. While
 * running, progress_current/progress_total are districts_done/total. */
export function useAdvocateSearchJob(jobId: number | null) {
  return useQuery({
    queryKey: advocateSearchKeys.searchJob(jobId ?? -1),
    queryFn: () => advocateSearchApi.getSearchStatus(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => jobPollInterval(query.state.data, SEARCH_POLL_MS),
    // Deliberately NOT polling in a hidden tab (refetchIntervalInBackground
    // is left at its default, false): every poll costs the server the whole
    // result payload, and a search runs for tens of minutes, so a forgotten
    // background tab was a steady drain. Polling resumes when the tab is
    // visible again (no focus refetch is needed -- the interval restarts).
    refetchOnWindowFocus: false,
  });
}

/** Enqueues a retry of just the failed/partial districts from a previous
 * search job. Returns a NEW job id -- the caller should switch its
 * polling to that id, same as starting a fresh search. */
export function useRetryFailedDistricts() {
  return useMutation({
    mutationFn: (jobId: number) => advocateSearchApi.retryFailedDistricts(jobId),
  });
}

export function useImportAdvocateCases() {
  return useMutation({
    mutationFn: ({
      courtType,
      selected,
      searchJobId,
    }: {
      courtType: CourtType;
      selected: AdvocateImportSelection[];
      searchJobId?: number;
    }) => advocateSearchApi.startImport(courtType, selected, searchJobId),
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
    refetchInterval: (query) => jobPollInterval(query.state.data, ACTIVE_POLL_MS),
    refetchOnWindowFocus: false,
  });
}
