import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { limitationApi } from "@/lib/api/limitation";
import { taskKeys } from "@/hooks/use-tasks";
import type { AddLimitationDeadlineInput, CourtType } from "@/types";

export const limitationKeys = {
  all: ["limitation"] as const,
  rules: (courtType?: CourtType | null) => [...limitationKeys.all, "rules", courtType ?? null] as const,
  compute: (ruleKey: string, triggerDate: string) =>
    [...limitationKeys.all, "compute", ruleKey, triggerDate] as const,
};

export function useLimitationRules(courtType?: CourtType | null, enabled = true) {
  return useQuery({
    queryKey: limitationKeys.rules(courtType),
    queryFn: () => limitationApi.rules(courtType),
    enabled,
    // Statutory periods: they change with the law, not between page views.
    staleTime: Infinity,
  });
}

/** The last day for a rule and start date, computed by the API (the only
 * place limitation arithmetic lives). */
export function useLimitationCompute(ruleKey: string, triggerDate: string) {
  return useQuery({
    queryKey: limitationKeys.compute(ruleKey, triggerDate),
    queryFn: () => limitationApi.compute(ruleKey, triggerDate),
    enabled: Boolean(ruleKey) && /^\d{4}-\d{2}-\d{2}$/.test(triggerDate),
    staleTime: Infinity,
  });
}

export function useAddLimitationDeadline() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, data }: { caseId: number; data: AddLimitationDeadlineInput }) =>
      limitationApi.addDeadline(caseId, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: taskKeys.all }),
  });
}
