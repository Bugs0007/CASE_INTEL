import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { hearingsApi } from "@/lib/api/hearings";
import type { Hearing, HearingCreateInput, HearingUpdateInput } from "@/types";

// Query keys factory
export const hearingKeys = {
  all: ["hearings"] as const,
  lists: () => [...hearingKeys.all, "list"] as const,
  list: (filters: {
    case_id?: number;
    status?: string;
    upcoming?: boolean;
    past?: boolean;
  }) => [...hearingKeys.lists(), filters] as const,
  details: () => [...hearingKeys.all, "detail"] as const,
  detail: (id: number) => [...hearingKeys.details(), id] as const,
};

// List hearings hook
export function useHearings(
  filters: {
    case_id?: number;
    status?: string;
    upcoming?: boolean;
    past?: boolean;
  } = {},
) {
  return useQuery({
    queryKey: hearingKeys.list(filters),
    queryFn: () => hearingsApi.list(filters),
    staleTime: 60 * 1000, // 1 minute -- hearings change often enough to keep this short
  });
}

// Get single hearing hook
export function useHearing(id: number) {
  return useQuery({
    queryKey: hearingKeys.detail(id),
    queryFn: () => hearingsApi.get(id),
    enabled: !!id,
  });
}

// Create hearing mutation
export function useCreateHearing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: HearingCreateInput) => hearingsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
    },
  });
}

// Update hearing mutation
export function useUpdateHearing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: HearingUpdateInput }) =>
      hearingsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: hearingKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
    },
  });
}

// Delete hearing mutation
export function useDeleteHearing() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => hearingsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
    },
  });
}
