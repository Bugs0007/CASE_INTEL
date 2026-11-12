import type {
  PracticeChatRequest,
  PracticeOverview,
  PracticeReportCard,
  PracticeReportFormat,
  PracticeTurn,
} from "@/types/practice";
import { apiBlob, apiClient } from "./client";

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

  /** A report file, built from the card's fields. Fetched as a blob: the
   * endpoint needs the auth header. Never a `format` query parameter. */
  report: (card: Pick<PracticeReportCard, "kind" | "date_from" | "date_to">, format: PracticeReportFormat) =>
    apiBlob(`/practice-assistant/reports/${card.kind}/${format}/`, {
      params: { date_from: card.date_from ?? "", date_to: card.date_to ?? "" },
    }),
};
