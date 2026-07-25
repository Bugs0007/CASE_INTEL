import { useMutation, useQueryClient } from "@tanstack/react-query";
import { clientContactsApi } from "@/lib/api/client-contacts";
import { caseKeys } from "@/hooks/use-cases";
import type { ClientContactInput } from "@/types";

// Client contacts are read off Case.client_contacts (nested, read-only --
// see CaseSerializer) rather than a separate list query, so these mutations
// only need to invalidate the owning case's detail query on success.

export function useCreateClientContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ClientContactInput) => clientContactsApi.create(data),
    onSuccess: (_, { case: caseId }) => {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
    },
  });
}

export function useUpdateClientContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      id,
      caseId,
      data,
    }: {
      id: number;
      caseId: number;
      data: Partial<ClientContactInput>;
    }) => clientContactsApi.update(id, data),
    onSuccess: (_, { caseId }) => {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
    },
  });
}

export function useDeleteClientContact() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id }: { id: number; caseId: number }) => clientContactsApi.delete(id),
    onSuccess: (_, { caseId }) => {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
    },
  });
}
