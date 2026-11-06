import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { casesApi } from "@/lib/api/cases";
import { ORDER_SYNC_POLL_MS, isOrderSyncActive } from "@/lib/order-sync";
import type { CaseCreateInput, CaseUpdateInput, CaseStatus } from "@/types";

export const caseKeys = {
  all: ["cases"] as const,
  lists: () => [...caseKeys.all, "list"] as const,
  list: (filters: { status?: CaseStatus | "all"; since?: string }) =>
    [...caseKeys.lists(), filters] as const,
  details: () => [...caseKeys.all, "detail"] as const,
  detail: (id: number) => [...caseKeys.details(), id] as const,
};

export function useCases(status?: CaseStatus | "all", since?: string) {
  return useQuery({
    queryKey: caseKeys.list({ status, since }),
    queryFn: () => casesApi.list(status === "all" ? undefined : status, since),
    staleTime: 60 * 1000, // 1 minute
  });
}

export function useCase(id: number, enabled: boolean = true) {
  return useQuery({
    queryKey: caseKeys.detail(id),
    queryFn: () => casesApi.get(id),
    enabled: !!id && enabled,
    staleTime: 60 * 1000, // 1 minute
    // While an order check is queued or running, re-read the case every 5
    // seconds; the interval turns itself off the moment it settles.
    refetchInterval: (query) =>
      isOrderSyncActive(query.state.data?.order_sync?.state) ? ORDER_SYNC_POLL_MS : false,
  });
}

export function useCreateCase() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CaseCreateInput) => casesApi.create(data),
    onSuccess: (createdCase) => {
      queryClient.setQueryData(caseKeys.detail(createdCase.id), createdCase);
      queryClient.invalidateQueries({ queryKey: caseKeys.lists() });
    },
  });
}

export function useUpdateCase() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: CaseUpdateInput }) =>
      casesApi.update(id, data),
    onSuccess: (updatedCase) => {
      queryClient.setQueryData(caseKeys.detail(updatedCase.id), updatedCase);
      queryClient.invalidateQueries({ queryKey: caseKeys.lists() });
    },
  });
}

export function useDeleteCase() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => casesApi.delete(id),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: caseKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: caseKeys.lists() });
    },
  });
}
