import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { chatApi, conversationsApi } from "@/lib/api/chat";
import type { ChatRequest, Conversation } from "@/types";

// Query keys factory
export const chatKeys = {
  all: ["chat"] as const,
  conversations: () => [...chatKeys.all, "conversations"] as const,
  conversation: (id: number) => [...chatKeys.conversations(), id] as const,
};

// List conversations hook
export function useConversations() {
  return useQuery({
    queryKey: chatKeys.conversations(),
    queryFn: () => conversationsApi.list(),
  });
}

// Get single conversation hook
export function useConversation(id: number) {
  return useQuery({
    queryKey: chatKeys.conversation(id),
    queryFn: () => conversationsApi.get(id),
    enabled: !!id,
  });
}

// Send chat message mutation
export function useSendChat() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ChatRequest) => chatApi.send(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    },
  });
}

// Delete conversation mutation
export function useDeleteConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => conversationsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    },
  });
}
