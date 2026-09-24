import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  billingPortfolioApi,
  clientMessagesApi,
  clientsApi,
  docTemplatesApi,
  refreshAllApi,
  sentMessagesApi,
  type ClientMessageFilters,
} from "@/lib/api/clients";
import { caseKeys } from "@/hooks/use-cases";
import { dashboardKeys } from "@/hooks/use-dashboard";
import { documentKeys } from "@/hooks/use-documents";
import { hearingKeys } from "@/hooks/use-hearings";
import type {
  ClientInput,
  ClientMessageUpdateInput,
  GenerateDocumentInput,
  RefreshRun,
} from "@/types";

/** Long enough for the new tab to load the PDF before the URL is released. */
const BLOB_REVOKE_DELAY_MS = 60_000;

export const clientKeys = {
  all: ["clients"] as const,
  list: (search?: string) => [...clientKeys.all, "list", search ?? ""] as const,
};

export const clientMessageKeys = {
  all: ["client-messages"] as const,
  list: (filters: ClientMessageFilters) => [...clientMessageKeys.all, "list", filters] as const,
  sent: (filters: { case_id?: number }) => [...clientMessageKeys.all, "sent", filters] as const,
};

export const billingPortfolioKeys = {
  all: ["billing-portfolio"] as const,
};

export const docTemplateKeys = {
  forCase: (caseId: number, contactId?: number | null) =>
    ["doc-templates", caseId, contactId ?? null] as const,
};

export const refreshAllKeys = {
  latest: ["refresh-all", "latest"] as const,
  run: (jobId: number) => ["refresh-all", jobId] as const,
};

// ---------------------------------------------------------------------------
// Clients
// ---------------------------------------------------------------------------

export function useClients(search?: string, enabled = true) {
  return useQuery({
    queryKey: clientKeys.list(search),
    queryFn: () => clientsApi.list(search),
    staleTime: 60 * 1000,
    enabled,
  });
}

export function useCreateClient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ClientInput) => clientsApi.create(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clientKeys.all }),
  });
}

export function useUpdateClient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ClientInput> }) =>
      clientsApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clientKeys.all });
      queryClient.invalidateQueries({ queryKey: billingPortfolioKeys.all });
      // Cases embed client_detail (name/type).
      queryClient.invalidateQueries({ queryKey: caseKeys.all });
    },
  });
}

export function useDeleteClient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => clientsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: clientKeys.all });
      queryClient.invalidateQueries({ queryKey: billingPortfolioKeys.all });
      queryClient.invalidateQueries({ queryKey: caseKeys.all });
    },
  });
}

/** Open a client's outstanding statement in a new tab. The tab is opened
 * during the click (a window.open after the await is blocked as a popup),
 * then pointed at the fetched blob -- same as useViewInvoice. */
export function useViewClientStatement() {
  return useMutation<string, unknown, number, { win: Window | null }>({
    mutationFn: async (clientId: number) => URL.createObjectURL(await clientsApi.statementPdf(clientId)),
    onMutate: () => ({ win: typeof window !== "undefined" ? window.open("", "_blank") : null }),
    onSuccess: (url, _id, context) => {
      if (context?.win) {
        context.win.location.href = url;
      } else if (typeof window !== "undefined") {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      setTimeout(() => URL.revokeObjectURL(url), BLOB_REVOKE_DELAY_MS);
    },
    onError: (_err, _id, context) => {
      context?.win?.close();
    },
  });
}

// ---------------------------------------------------------------------------
// Billing portfolio
// ---------------------------------------------------------------------------

export function useBillingPortfolio() {
  return useQuery({
    queryKey: billingPortfolioKeys.all,
    queryFn: () => billingPortfolioApi.get(),
    staleTime: 30 * 1000,
  });
}

// ---------------------------------------------------------------------------
// Client messages (drafts inbox)
// ---------------------------------------------------------------------------

export function useClientMessages(filters: ClientMessageFilters, enabled = true) {
  return useQuery({
    queryKey: clientMessageKeys.list(filters),
    queryFn: () => clientMessagesApi.list(filters),
    enabled,
    staleTime: 30 * 1000,
  });
}

export function useSentMessages(filters: { case_id?: number } = {}) {
  return useQuery({
    queryKey: clientMessageKeys.sent(filters),
    queryFn: () => sentMessagesApi.list(filters),
    staleTime: 30 * 1000,
  });
}

export function useUpdateClientMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ClientMessageUpdateInput }) =>
      clientMessagesApi.update(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clientMessageKeys.all }),
  });
}

export function useDiscardClientMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => clientMessagesApi.discard(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: clientMessageKeys.all }),
  });
}

/** Resolves (does NOT reject) with sent=false when the server has no email
 * credentials -- callers must branch on result.sent. */
export function useSendClientMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => clientMessagesApi.send(id),
    onSettled: () => queryClient.invalidateQueries({ queryKey: clientMessageKeys.all }),
  });
}

// ---------------------------------------------------------------------------
// Document templates
// ---------------------------------------------------------------------------

export function useDocTemplatesForCase(caseId: number, contactId: number | null, enabled = true) {
  return useQuery({
    queryKey: docTemplateKeys.forCase(caseId, contactId),
    queryFn: () => docTemplatesApi.forCase(caseId, contactId),
    enabled: enabled && !!caseId,
  });
}

export function useGenerateDocument(caseId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: GenerateDocumentInput) => docTemplatesApi.generate(caseId, data),
    onSuccess: (_doc, data) => {
      queryClient.invalidateQueries({ queryKey: documentKeys.lists() });
      if (data.save?.length) {
        // Answers written back to the case, contact or profile.
        queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
        queryClient.invalidateQueries({ queryKey: ["advocate-profile"] });
        queryClient.invalidateQueries({ queryKey: ["doc-templates", caseId] });
      }
    },
  });
}

// ---------------------------------------------------------------------------
// Refresh all tracked cases
// ---------------------------------------------------------------------------

const ACTIVE = new Set<RefreshRun["status"]>(["queued", "running"]);

export function isRunActive(run: RefreshRun | null | undefined): boolean {
  return !!run && ACTIVE.has(run.status);
}

/** The caller's latest run -- so a reloaded dashboard picks the progress
 * bar back up. */
export function useLatestRefreshRun() {
  return useQuery({ queryKey: refreshAllKeys.latest, queryFn: () => refreshAllApi.latest() });
}

/** Polls a run every 3s while it's active; stops by itself when it ends,
 * and refreshes everything a refresh can change (cases, hearings, drafts). */
export function useRefreshRun(jobId: number | null) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: refreshAllKeys.run(jobId ?? 0),
    queryFn: () => refreshAllApi.status(jobId as number),
    enabled: jobId !== null,
    refetchInterval: (q) => (isRunActive(q.state.data) ? 3000 : false),
  });
  const finished = query.data && !isRunActive(query.data);
  useEffect(() => {
    if (finished) {
      queryClient.invalidateQueries({ queryKey: caseKeys.all });
      queryClient.invalidateQueries({ queryKey: hearingKeys.all });
      queryClient.invalidateQueries({ queryKey: dashboardKeys.all });
      queryClient.invalidateQueries({ queryKey: clientMessageKeys.all });
    }
  }, [finished, queryClient]);
  return query;
}

export function useStartRefreshAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => refreshAllApi.start(),
    onSuccess: (run) => {
      queryClient.setQueryData(refreshAllKeys.run(run.job_id), run);
      queryClient.setQueryData(refreshAllKeys.latest, run);
    },
  });
}

export function useCancelRefreshAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: number) => refreshAllApi.cancel(jobId),
    onSuccess: (run) => queryClient.setQueryData(refreshAllKeys.run(run.job_id), run),
  });
}
