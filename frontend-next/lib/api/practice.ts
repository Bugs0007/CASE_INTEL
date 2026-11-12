import type { PracticeChatRequest, PracticeOverview, PracticeTurn } from "@/types/practice";
import { apiClient } from "./client";

export interface PracticeOverviewParams {
  /** YYYY-MM-DD, India day */
  from: string;
  /** YYYY-MM-DD, inclusive */
  to: string;
  /** 1-based page of the portfolio's case list */
  casePage: number;
}

export const practiceApi = {
  overview: ({ from, to, casePage }: PracticeOverviewParams) =>
    apiClient<PracticeOverview>("/practice-assistant/overview/", {
      params: { from, to, case_page: casePage },
    }),

  /** Replaying the same client_request_id returns the same turn. */
  chat: (data: PracticeChatRequest) =>
    apiClient<PracticeTurn>("/practice-assistant/chat/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};
