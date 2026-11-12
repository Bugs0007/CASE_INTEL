import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { chatApi, conversationsApi } from "@/lib/api/chat";
import type { ChatRequest, Conversation } from "@/types";

// Query keys factory
export const chatKeys = {
  all: ["chat"] as const,
  conversations: () => [...chatKeys.all, "conversations"] as const,
  conversation: (id: number) => [...chatKeys.conversations(), id] as const,
  list: (scope: "practice" | "default") => [...chatKeys.conversations(), "list", scope] as const,
  messages: (id: number) => [...chatKeys.all, "messages", id] as const,
};

/** The sidebar's lists: case and older document chats (default) or practice
 * chats. Practice chats are never in the default list. */
export function useConversationList(scope: "practice" | "default", enabled = true) {
  return useQuery({
    queryKey: chatKeys.list(scope),
    queryFn: () => conversationsApi.list(undefined, scope === "practice" ? "practice" : undefined),
    enabled,
  });
}

/** A conversation's messages, always re-read when it is opened: a chat that
 * was continued elsewhere must not show its old copy. */
export function useConversationMessages(id: number | null) {
  return useQuery({
    queryKey: chatKeys.messages(id ?? 0),
    queryFn: () => conversationsApi.getMessages(id as number),
    enabled: id !== null,
    staleTime: 0,
    refetchOnMount: "always",
  });
}

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
    onSuccess: (_result, id) => {
      queryClient.removeQueries({ queryKey: chatKeys.messages(id) });
      queryClient.invalidateQueries({ queryKey: chatKeys.conversations() });
    },
  });
}
