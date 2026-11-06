import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { advocateSearchApi } from "@/lib/api/advocate-search";
import { advocateSearchKeys } from "@/hooks/use-advocate-search";
import { relabelRows } from "@/lib/advocate-search-results";
import type {
  AdvocateProfileInput,
  AdvocateSearchJobResult,
  AdvocateSearchProfile,
  CourtsStatus,
  StartSearchV2Request,
} from "@/types";

// Hooks for the redesigned advocate search (ADVOCATE_SEARCH_V2).

const COURTS_POLL_MS = 3000;

export const advocateV2Keys = {
  features: ["advocate-search", "features"] as const,
  profiles: ["advocate-search", "profiles"] as const,
  courts: (jobId: number) => ["advocate-search", "courts", jobId] as const,
  active: ["advocate-search", "active"] as const,
  highCourts: ["advocate-search", "high-courts"] as const,
  benches: (code: string) => ["advocate-search", "high-courts", code, "benches"] as const,
};

/** Is the redesigned search switched on? Anything but a clean "yes" (including a
 * failed request) reads as off, so the old page is what loads. */
export function useAdvocateFeatures() {
  return useQuery({
    queryKey: advocateV2Keys.features,
    queryFn: () => advocateSearchApi.features(),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useAdvocateProfiles() {
  return useQuery({
    queryKey: advocateV2Keys.profiles,
    queryFn: () => advocateSearchApi.listProfiles(),
    staleTime: 30 * 1000,
  });
}

function useProfileCache() {
  const queryClient = useQueryClient();
  return (profile: AdvocateSearchProfile) =>
    queryClient.setQueryData<AdvocateSearchProfile[]>(advocateV2Keys.profiles, (old) => {
      const list = old ?? [];
      return list.some((p) => p.id === profile.id) ? list.map((p) => (p.id === profile.id ? profile : p)) : [...list, profile];
    });
}

export function useCreateProfile() {
  const cache = useProfileCache();
  return useMutation({
    mutationFn: (body: AdvocateProfileInput) => advocateSearchApi.createProfile(body),
    onSuccess: cache,
  });
}

export function useUpdateProfile() {
  const cache = useProfileCache();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<AdvocateProfileInput> }) =>
      advocateSearchApi.updateProfile(id, body),
    onSuccess: cache,
  });
}

/** "Not me" / "That's me" on a name. With a search open, the rows that list the
 * name move on screen at once and the server's answer replaces the guess; the
 * profile in the cache is replaced by what the server returns. No new search. */
export function useNameAction(jobId: number | null) {
  const queryClient = useQueryClient();
  const cache = useProfileCache();
  return useMutation({
    mutationFn: ({ profileId, name, action }: { profileId: number; name: string; action: "exclude" | "add" }) =>
      action === "exclude"
        ? advocateSearchApi.excludeName(profileId, name)
        : advocateSearchApi.addNameForm(profileId, name),
    onMutate: async ({ name, action }) => {
      if (jobId === null) return { previous: undefined };
      const key = advocateSearchKeys.searchJob(jobId);
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<AdvocateSearchJobResult>(key);
      if (previous) {
        const { rows, counts } = relabelRows(previous.results, name, action);
        queryClient.setQueryData<AdvocateSearchJobResult>(key, { ...previous, results: rows, match_counts: counts });
      }
      return { previous };
    },
    onError: (_error, _vars, context) => {
      if (jobId !== null && context?.previous) {
        queryClient.setQueryData(advocateSearchKeys.searchJob(jobId), context.previous);
      }
    },
    onSuccess: cache,
    onSettled: () => {
      if (jobId !== null) queryClient.invalidateQueries({ queryKey: advocateSearchKeys.searchJob(jobId) });
    },
  });
}

export function useStartSearchV2() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StartSearchV2Request) => advocateSearchApi.searchV2(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: advocateSearchKeys.preference }),
  });
}

/** Court-by-court status: polled while the search runs or a retry is running,
 * then left alone. */
export function useCourtsStatus(jobId: number | null) {
  return useQuery({
    queryKey: advocateV2Keys.courts(jobId ?? -1),
    queryFn: () => advocateSearchApi.getCourts(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const data = query.state.data as CourtsStatus | undefined;
      if (!data) return false;
      const running = data.job.status === "queued" || data.job.status === "running";
      return running || data.job.is_retrying ? COURTS_POLL_MS : false;
    },
    refetchOnWindowFocus: false,
  });
}

export function useRetryCourts(jobId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { only_failed: true } | { complex_ids: number[] }) => advocateSearchApi.retryCourts(jobId!, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: advocateV2Keys.courts(jobId ?? -1) });
      queryClient.invalidateQueries({ queryKey: advocateSearchKeys.searchJob(jobId ?? -1) });
    },
  });
}

export function useCancelSearch(jobId: number | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => advocateSearchApi.cancelSearch(jobId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: advocateV2Keys.courts(jobId ?? -1) });
      queryClient.invalidateQueries({ queryKey: advocateSearchKeys.searchJob(jobId ?? -1) });
    },
  });
}

/** The caller's running searches, asked once when the page opens without one. */
export function useActiveSearches(enabled: boolean) {
  return useQuery({
    queryKey: advocateV2Keys.active,
    queryFn: () => advocateSearchApi.listActive(),
    enabled,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
}

export function useHighCourts() {
  return useQuery({
    queryKey: advocateV2Keys.highCourts,
    queryFn: () => advocateSearchApi.listHighCourts(),
    staleTime: 60 * 60 * 1000,
    select: (data) => data.courts,
  });
}

/** One court's benches as the portal lists them (a CAPTCHA-free call). */
export function useHighCourtBenches(code: string | null) {
  return useQuery({
    queryKey: advocateV2Keys.benches(code ?? ""),
    queryFn: () => advocateSearchApi.highCourtBenches(code!),
    enabled: !!code,
    staleTime: 60 * 60 * 1000,
    retry: false,
  });
}
