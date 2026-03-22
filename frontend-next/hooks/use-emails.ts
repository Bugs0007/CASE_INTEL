import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { emailsApi } from "@/lib/api/emails";
import type { Email } from "@/types";

// Query keys factory
export const emailKeys = {
  all: ["emails"] as const,
  lists: () => [...emailKeys.all, "list"] as const,
  list: (filters: { case_id?: number; linked_status?: string }) =>
    [...emailKeys.lists(), filters] as const,
};

// List emails hook
export function useEmails(
  filters: {
    case_id?: number;
    linked_status?: string;
  } = {},
) {
  return useQuery({
    queryKey: emailKeys.list(filters),
    queryFn: () => emailsApi.list(filters),
  });
}

// Link email to case mutation
export function useLinkEmail() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ emailId, caseId }: { emailId: number; caseId: number }) =>
      emailsApi.linkToCase(emailId, caseId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: emailKeys.lists() });
    },
  });
}
