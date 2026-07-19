import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { documentsApi } from "@/lib/api/documents";
import { isDocumentActive } from "@/components/documents/document-status-badge";
import type {
  Document,
  DocumentUploadInput,
  DocumentUpdateInput,
  ProcessingStatus,
} from "@/types";

// While any listed document has background work queued/running, poll so
// the row's "Processing… X/Y" progress stays live.
const ACTIVE_POLL_MS = 2500;

type DocumentFilters = {
  case_id?: number;
  document_type?: string;
  processing_status?: ProcessingStatus;
};

export const documentKeys = {
  all: ["documents"] as const,
  lists: () => [...documentKeys.all, "list"] as const,
  list: (filters: DocumentFilters) => [...documentKeys.lists(), filters] as const,
  details: () => [...documentKeys.all, "detail"] as const,
  detail: (id: number) => [...documentKeys.details(), id] as const,
};

export function useDocuments(filters: DocumentFilters = {}) {
  return useQuery({
    queryKey: documentKeys.list(filters),
    queryFn: () => documentsApi.list(filters),
    staleTime: 60 * 1000,
    refetchInterval: (query) =>
      query.state.data?.some(isDocumentActive) ? ACTIVE_POLL_MS : false,
  });
}

export function useDocument(id: number, enabled: boolean = true) {
  return useQuery({
    queryKey: documentKeys.detail(id),
    queryFn: () => documentsApi.get(id),
    enabled: !!id && enabled,
    staleTime: 60 * 1000,
    refetchInterval: (query) =>
      query.state.data && isDocumentActive(query.state.data)
        ? ACTIVE_POLL_MS
        : false,
  });
}

// Upload document mutation
export function useUploadDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: DocumentUploadInput) => documentsApi.upload(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}

// Update document mutation
export function useUpdateDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: DocumentUpdateInput }) =>
      documentsApi.update(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}

// Process document mutation
export function useProcessDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => documentsApi.process(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.detail(id) });
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}

// Delete document mutation
export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => documentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
    },
  });
}
