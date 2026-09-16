import { apiClient } from "./client";
import type {
  AddLimitationDeadlineInput,
  AddLimitationDeadlineResponse,
  CourtType,
  LimitationComputation,
  LimitationRule,
} from "@/types";

export const limitationApi = {
  rules: (courtType?: CourtType | null) =>
    apiClient<LimitationRule[]>("/limitation/rules/", {
      params: { court_type: courtType ?? undefined },
    }),

  compute: (ruleKey: string, triggerDate: string) =>
    apiClient<LimitationComputation>("/limitation/compute/", {
      params: { rule_key: ruleKey, trigger_date: triggerDate },
    }),

  addDeadline: (caseId: number, data: AddLimitationDeadlineInput) =>
    apiClient<AddLimitationDeadlineResponse>(`/cases/${caseId}/limitation-deadlines/`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
