import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { caseEventsApi } from "@/lib/api/case-events";
import type { CaseEventFilters, CaseEventInput } from "@/types";

export const caseEventKeys = {
  all: ["case-events"] as const,
  lists: () => [...caseEventKeys.all, "list"] as const,
  list: (filters: CaseEventFilters) => [...caseEventKeys.lists(), filters] as const,
};

export function useCaseEvents(filters: CaseEventFilters = {}) {
  return useQuery({
    queryKey: caseEventKeys.list(filters),
    queryFn: () => caseEventsApi.list(filters),
    staleTime: 60 * 1000,
  });
}

// Every mutation invalidates every event list: the same event appears on its
// case page and on the global calendar, under different filters.

export function useCreateCaseEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CaseEventInput) => caseEventsApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseEventKeys.all }),
  });
}

export function useUpdateCaseEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<CaseEventInput> }) =>
      caseEventsApi.update(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseEventKeys.all }),
  });
}

export function useDeleteCaseEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => caseEventsApi.delete(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseEventKeys.all }),
  });
}
