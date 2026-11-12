import type { PracticeMessage } from "@/components/dashboard/practice/practice-assistant-panel";
import type { Message } from "@/types/chat";
import type {
  PracticeAnyActionCard,
  PracticeReportCard,
  PracticeCaseCandidate,
  PracticeIntent,
  PracticeReference,
  PracticeTurn,
  PracticeTurnStatus,
} from "@/types/practice";

/** What the server stores on a practice chat's user message: the request id
 * and the turn it produced. Only the parts a past turn needs are read. */
interface RequestMarker {
  kind: "practice_request";
  turn?: {
    intent?: PracticeIntent | null;
    status?: PracticeTurnStatus;
    summary?: Record<string, unknown> | null;
    case_candidates?: PracticeCaseCandidate[];
    action_card?: PracticeAnyActionCard | null;
    report?: PracticeReportCard | null;
    as_of?: string;
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function markerOf(message: Message): RequestMarker | null {
  const found = (message.references ?? []).find((ref) => isRecord(ref) && ref.kind === "practice_request");
  return (found as RequestMarker | undefined) ?? null;
}

function sourcesOf(message: Message): PracticeReference[] {
  return (message.references ?? []).filter(
    (ref): ref is PracticeReference => isRecord(ref) && ref.kind !== "practice_request" && typeof ref.id === "number",
  );
}

/** Rebuilds a past practice chat for display: the answer is the assistant
 * message, its sources are the assistant message's references, and the case
 * choices and invoice card come from the request marker on the user message
 * before it. A replayed invoice card is only a proposal: it sends nothing
 * until the advocate presses Send invoice and then Confirm. */
export function rebuildPracticeMessages(messages: Message[], conversationId: number): PracticeMessage[] {
  const rebuilt: PracticeMessage[] = [];
  let marker: RequestMarker | null = null;
  let userMessageId = 0;
  for (const message of messages) {
    if (message.role === "user") {
      marker = markerOf(message);
      userMessageId = message.id;
      rebuilt.push({ role: "user", id: `m-${message.id}`, text: message.content });
    } else if (message.role === "assistant") {
      const turn = marker?.turn;
      rebuilt.push({
        role: "assistant",
        id: `m-${message.id}`,
        turn: {
          conversation_id: conversationId,
          user_message_id: userMessageId,
          assistant_message_id: message.id,
          answer: message.content,
          intent: turn?.intent ?? null,
          status: turn?.status ?? "answer",
          sources: sourcesOf(message),
          summary: turn?.summary ?? null,
          case_candidates: turn?.case_candidates ?? [],
          action_card: turn?.action_card ?? null,
          report: turn?.report ?? null,
          as_of: turn?.as_of ?? message.created_at,
        } satisfies PracticeTurn,
      });
      marker = null;
    }
  }
  return rebuilt;
}
