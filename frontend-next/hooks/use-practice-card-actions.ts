import { useMemo } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { appearanceFeesApi } from "@/lib/api/billing";
import { draftsApi } from "@/lib/api/drafts";
import { tasksApi } from "@/lib/api/tasks";
import { taskKeys } from "@/hooks/use-tasks";
import { caseKeys } from "@/hooks/use-cases";
import { billingFeeKeys } from "@/hooks/use-billing";
import { billingPortfolioKeys } from "@/hooks/use-clients";
import { hearingKeys } from "@/hooks/use-hearings";
import { draftKeys } from "@/hooks/use-drafts";
import type { AppearanceFeeCreateInput, TaskInput } from "@/types";
import type { DraftCreateRequest, DraftSubtype } from "@/types/draft";
import type { PracticeDraftSubtype, PracticeFeeFields } from "@/types/practice";

export interface PracticeCardActions {
  createFee: (caseId: number, input: AppearanceFeeCreateInput) => Promise<unknown>;
  updateFee: (caseId: number, feeId: number, proposed: PracticeFeeFields) => Promise<unknown>;
  generateInvoice: (caseId: number, feeId: number) => Promise<unknown>;
  deleteFee: (caseId: number, feeId: number) => Promise<unknown>;
  markPaid: (caseId: number, feeId: number) => Promise<unknown>;
  sendInvoice: (caseId: number, feeId: number) => Promise<unknown>;
  createTask: (input: TaskInput) => Promise<unknown>;
  /** Resolves with the new draft's id. */
  createDraft: (input: {
    caseId: number;
    subtype: PracticeDraftSubtype;
    instructions: string;
    clientRequestId: string;
  }) => Promise<number>;
}

/** The existing owner-scoped endpoints an action card confirms through. Each
 * is called only from a card's Confirm button; a billing change refreshes
 * the billing and case queries afterwards. */
export function usePracticeCardActions(): PracticeCardActions {
  const queryClient = useQueryClient();
  return useMemo(() => {
    function refreshBilling(caseId: number) {
      queryClient.invalidateQueries({ queryKey: caseKeys.detail(caseId) });
      queryClient.invalidateQueries({ queryKey: hearingKeys.lists() });
      queryClient.invalidateQueries({ queryKey: billingFeeKeys.all });
      queryClient.invalidateQueries({ queryKey: billingPortfolioKeys.all });
    }
    return {
      createFee: async (caseId, input) => {
        const fee = await appearanceFeesApi.create(input);
        refreshBilling(caseId);
        return fee;
      },
      updateFee: async (caseId, feeId, proposed) => {
        const fee = await appearanceFeesApi.update(feeId, proposed);
        refreshBilling(caseId);
        return fee;
      },
      generateInvoice: async (caseId, feeId) => {
        const fee = await appearanceFeesApi.generateInvoice(feeId);
        refreshBilling(caseId);
        return fee;
      },
      deleteFee: async (caseId, feeId) => {
        await appearanceFeesApi.delete(feeId);
        refreshBilling(caseId);
      },
      markPaid: async (caseId, feeId) => {
        const fee = await appearanceFeesApi.markPaid(feeId);
        refreshBilling(caseId);
        return fee;
      },
      sendInvoice: async (caseId, feeId) => {
        const result = await appearanceFeesApi.send(feeId);
        refreshBilling(caseId);
        return result;
      },
      createTask: async (input) => {
        const task = await tasksApi.create(input);
        queryClient.invalidateQueries({ queryKey: taskKeys.all });
        if (input.case) queryClient.invalidateQueries({ queryKey: caseKeys.detail(input.case) });
        return task;
      },
      createDraft: async ({ caseId, subtype, instructions, clientRequestId }) => {
        const request: DraftCreateRequest = {
          case_id: caseId,
          // The server knows the two new kinds; the shared draft type lists two.
          subtype: subtype as DraftSubtype,
          instructions,
          client_request_id: clientRequestId,
        };
        const draft = await draftsApi.create(request);
        queryClient.invalidateQueries({ queryKey: draftKeys.list(caseId) });
        return draft.id;
      },
    };
  }, [queryClient]);
}
