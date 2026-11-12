import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { caseNotesApi, draftsApi } from "@/lib/api/drafts";
import type {
  DraftApproveRequest,
  DraftCreateRequest,
  DraftDetail,
  DraftOutput,
  DraftOutputRequest,
  DraftRevisionCreateRequest,
} from "@/types/draft";

const POLL_MS = 2500;
/** Saved to disk after a download so the object URL can be revoked. */
const BLOB_REVOKE_DELAY_MS = 10_000;

export const draftKeys = {
  all: ["drafts"] as const,
  list: (caseId: number) => [...draftKeys.all, "list", caseId] as const,
  detail: (id: number) => [...draftKeys.all, "detail", id] as const,
  revision: (id: number, version: number) => [...draftKeys.all, "revision", id, version] as const,
};

export const caseNoteKeys = {
  all: ["case-notes"] as const,
  list: (caseId: number) => [...caseNoteKeys.all, "list", caseId] as const,
};

export function isDraftBusy(draft: DraftDetail | undefined): boolean {
  if (!draft) return false;
  return (
    draft.status === "queued" ||
    draft.status === "generating" ||
    draft.outputs.some((output) => output.status === "pending")
  );
}

export function useDrafts(caseId: number, enabled = true) {
  return useQuery({
    queryKey: draftKeys.list(caseId),
    queryFn: () => draftsApi.list(caseId),
    enabled,
  });
}

/** Polls every 2.5 s while the draft is generating (or an export is
 * pending), and not while the tab is hidden. */
export function useDraft(id: number | null) {
  return useQuery({
    queryKey: draftKeys.detail(id ?? 0),
    queryFn: () => draftsApi.get(id as number),
    enabled: id !== null,
    refetchInterval: (query) =>
      isDraftBusy(query.state.data) && typeof document !== "undefined" && !document.hidden ? POLL_MS : false,
  });
}

export function useDraftRevision(id: number, version: number | null) {
  return useQuery({
    queryKey: draftKeys.revision(id, version ?? 0),
    queryFn: () => draftsApi.revision(id, version as number),
    enabled: version !== null,
  });
}

function useStoreDetail(caseId: number) {
  const queryClient = useQueryClient();
  return (detail: DraftDetail) => {
    queryClient.setQueryData(draftKeys.detail(detail.id), detail);
    queryClient.invalidateQueries({ queryKey: draftKeys.list(caseId) });
  };
}

export function useCreateDraft(caseId: number) {
  const store = useStoreDetail(caseId);
  return useMutation({ mutationFn: (data: DraftCreateRequest) => draftsApi.create(data), onSuccess: store });
}

export function useSaveRevision(caseId: number, id: number) {
  const store = useStoreDetail(caseId);
  return useMutation({
    mutationFn: (data: DraftRevisionCreateRequest) => draftsApi.saveRevision(id, data),
    onSuccess: store,
  });
}

export function useRetryDraft(caseId: number, id: number) {
  const store = useStoreDetail(caseId);
  return useMutation({ mutationFn: () => draftsApi.retry(id), onSuccess: store });
}

export function useApproveDraft(caseId: number, id: number) {
  const store = useStoreDetail(caseId);
  return useMutation({ mutationFn: (data: DraftApproveRequest) => draftsApi.approve(id, data), onSuccess: store });
}

export function useCreateOutput(caseId: number, id: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: DraftOutputRequest) => draftsApi.createOutput(id, data),
    onSuccess: (output: DraftOutput) => {
      queryClient.invalidateQueries({ queryKey: draftKeys.detail(id) });
      if (output.destination === "case_note") {
        queryClient.invalidateQueries({ queryKey: caseNoteKeys.list(caseId) });
      }
    },
  });
}

/** Fetches the file with the auth header and saves it under `filename`. */
export function useDownloadOutput() {
  return useMutation({
    mutationFn: async ({ outputId, filename }: { outputId: number; filename: string }) => {
      const blob = await draftsApi.downloadOutput(outputId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename || "draft.docx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), BLOB_REVOKE_DELAY_MS);
    },
  });
}

export function useCaseNotes(caseId: number) {
  return useQuery({ queryKey: caseNoteKeys.list(caseId), queryFn: () => caseNotesApi.list(caseId), retry: false });
}

export function useDeleteCaseNote(caseId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => caseNotesApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: caseNoteKeys.list(caseId) }),
  });
}
