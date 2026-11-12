import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { APIError } from "@/lib/api/client";
import { appearanceFeesApi } from "@/lib/api/billing";
import { practiceApi, type PracticeOverviewParams } from "@/lib/api/practice";
import { getUsername } from "@/lib/auth";
import { caseKeys } from "@/hooks/use-cases";
import { billingFeeKeys } from "@/hooks/use-billing";
import { billingPortfolioKeys } from "@/hooks/use-clients";
import { hearingKeys } from "@/hooks/use-hearings";
import type { PracticeChatRequest } from "@/types/practice";

/** The signed-in username is part of the key: sign-out does not empty the
 * query cache, so without it a second user in the same tab would be served
 * the first user's overview until it went stale. */
export const practiceKeys = {
  all: ["practice"] as const,
  overview: (p: PracticeOverviewParams) =>
    [...practiceKeys.all, "overview", getUsername() ?? "", p.from, p.to, p.casePage] as const,
};

/** True when the server answered 404: the assistant is switched off there. */
export function isPracticeUnavailable(error: unknown): boolean {
  return error instanceof APIError && error.status === 404;
}

export function usePracticeOverview(params: PracticeOverviewParams) {
  return useQuery({
    queryKey: practiceKeys.overview(params),
    queryFn: () => practiceApi.overview(params),
    // A 404 is a settled answer, not a blip worth retrying.
    retry: (count, error) => !isPracticeUnavailable(error) && count < 1,
  });
}

export function useSendPracticeChat() {
  return useMutation({ mutationFn: (request: PracticeChatRequest) => practiceApi.chat(request) });
}

/** Confirm an invoice card: the existing send endpoint, one fee at a time.
 * Resolves with sent=false when the server only logged it. */
export function useConfirmPracticeInvoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ feeId }: { feeId: number; caseId: number }) => appearanceFeesApi.send(feeId),
    onSuccess: (_result, { caseId }) => {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
      queryClient.invalidateQueries({ queryKey: billingFeeKeys.all });
      queryClient.invalidateQueries({ queryKey: billingPortfolioKeys.all });
    },
  });
}
