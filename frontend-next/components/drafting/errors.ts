import { APIError, apiErrorDetail } from "@/lib/api/client";
import type { DraftErrorCode } from "@/types/draft";

export interface DraftProblem {
  code?: DraftErrorCode;
  message: string;
  /** Lines to list under the message (errors, items). */
  items: string[];
  currentRevisionId?: number;
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

/** Turns an API failure into copy for the screen. Server text is shown as
 * plain text only. */
export function describeDraftError(error: unknown, fallback: string): DraftProblem {
  const data =
    error instanceof APIError && error.data && typeof error.data === "object"
      ? (error.data as Record<string, unknown>)
      : {};
  const code = typeof data.code === "string" ? (data.code as DraftErrorCode) : undefined;
  switch (code) {
    case "draft_limit":
      return { code, message: "Too many drafts are still being written. Wait for one to finish, then try again.", items: [] };
    case "stale_revision":
      return {
        code,
        message: "This draft changed elsewhere.",
        items: [],
        currentRevisionId: typeof data.current_revision_id === "number" ? data.current_revision_id : undefined,
      };
    case "invalid_body":
      return { code, message: "The draft could not be saved. Fix these and try again.", items: strings(data.errors) };
    case "needs_acknowledgement":
      return { code, message: "Confirm that you have checked these items before approving.", items: strings(data.items) };
    case "evidence_changed":
      return {
        code,
        message:
          "These records changed or were removed since the draft was written. Generate a new draft or review them first.",
        items: strings(data.items),
      };
    default:
      return { code, message: apiErrorDetail(error, fallback), items: [] };
  }
}
