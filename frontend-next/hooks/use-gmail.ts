import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { gmailApi } from "@/lib/api/gmail";
import type { SyncConfig } from "@/types";

// Query keys factory
export const gmailKeys = {
  all: ["gmail"] as const,
  status: () => [...gmailKeys.all, "status"] as const,
};

// Get Gmail connection status hook
export function useGmailStatus() {
  return useQuery({
    queryKey: gmailKeys.status(),
    queryFn: () => gmailApi.getStatus(),
  });
}

// Sync emails mutation
export function useSyncEmails() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (config: SyncConfig) => gmailApi.sync(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gmailKeys.status() });
      queryClient.invalidateQueries({ queryKey: ["emails"] });
    },
  });
}
