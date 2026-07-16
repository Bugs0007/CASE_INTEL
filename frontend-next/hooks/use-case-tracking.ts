import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { caseTrackingApi } from "@/lib/api/case-tracking";
import { caseKeys } from "@/hooks/use-cases";
import { hearingKeys } from "@/hooks/use-hearings";
import type { CourtType, TrackingConfig } from "@/types";

export const courtStructureKeys = {
  all: ["court-structure"] as const,
  level: (params: Record<string, string | undefined>) =>
    [...courtStructureKeys.all, params] as const,
};

/** Cascading dropdown data for the tracking setup form. Each distinct
 * params combination is its own cache entry, and the backend caches
 * aggressively too (this data changes ~never), so this is cheap to call
 * on every dropdown change. */
export function useCourtStructure(
  params: {
    court_type: CourtType;
    state_code?: string;
    dist_code?: string;
    court_complex_code?: string;
    est_code?: string;
    hc_court_code?: string;
    bench_code?: string;
  } | null,
) {
  return useQuery({
    queryKey: courtStructureKeys.level(params ?? {}),
    queryFn: () => caseTrackingApi.courtStructure(params!),
    enabled: params !== null,
    staleTime: 24 * 60 * 60 * 1000, // 24h client-side; backend caches 30d
  });
}

/** Fetches live court data without persisting it. Doesn't invalidate any
 * queries -- nothing changed on the server yet. */
export function usePreviewTracking(caseId: number) {
  return useMutation({
    mutationFn: (config: TrackingConfig) => caseTrackingApi.preview(caseId, config),
  });
}

export function useConfirmTracking(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (previewToken: string) => caseTrackingApi.confirm(caseId, previewToken),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
    },
  });
}

export function useUntrackTracking(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => caseTrackingApi.untrack(caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
    },
  });
}

export function useRefreshTracking(caseId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (force: boolean) => caseTrackingApi.refresh(caseId, force),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
    },
  });
}
