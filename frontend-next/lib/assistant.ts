import type { AssistantScope } from "@/providers/assistant-provider";
import type { Conversation } from "@/types/chat";

/** The full page for a chat: an existing one by id, or a new one in a scope. */
export function assistantHref(scope: AssistantScope | null, conversationId: number | null): string {
  if (conversationId !== null) return `/assistant?c=${conversationId}`;
  if (scope === null) return "/assistant";
  return scope.kind === "practice" ? "/assistant?scope=practice" : `/assistant?case=${scope.caseId}`;
}

export function chatTitle(conversation: Pick<Conversation, "title">): string {
  return conversation.title || "Conversation";
}

/** When a chat was last active: its last message, else when it started. */
export function chatTime(conversation: Pick<Conversation, "last_message_at" | "started_at">): string {
  return conversation.last_message_at ?? conversation.started_at;
}

function newestFirst(a: Conversation, b: Conversation): number {
  return Date.parse(chatTime(b)) - Date.parse(chatTime(a));
}

export interface CaseChatGroup {
  caseId: number;
  title: string;
  chats: Conversation[];
}

export interface ChatGroups {
  practice: Conversation[];
  cases: CaseChatGroup[];
  legacy: Conversation[];
}

/** The sidebar's groups from the conversation lists. Practice and legacy
 * chats are newest first; each case is a group of its own, its chats newest
 * first, and the groups are ordered by their latest chat. The filter matches
 * chat titles and case titles: a matching case title keeps all its chats. */
export function groupConversations(rows: Conversation[], filter: string): ChatGroups {
  const needle = filter.trim().toLowerCase();
  const matches = (text: string) => !needle || text.toLowerCase().includes(needle);

  const practice = rows.filter((row) => row.scope === "practice" && matches(chatTitle(row)));
  const legacy = rows.filter((row) => row.scope === "legacy_documents" && matches(chatTitle(row)));

  const byCase = new Map<number, { title: string; chats: Conversation[] }>();
  for (const row of rows) {
    if (row.scope !== "case" && row.scope !== undefined) continue;
    if (row.case_id === null) continue;
    const group = byCase.get(row.case_id) ?? { title: row.case_title || `Case ${row.case_id}`, chats: [] };
    group.chats.push(row);
    byCase.set(row.case_id, group);
  }
  const cases: CaseChatGroup[] = [];
  for (const [caseId, group] of byCase) {
    const chats = matches(group.title) ? group.chats : group.chats.filter((row) => matches(chatTitle(row)));
    if (chats.length > 0) cases.push({ caseId, title: group.title, chats: [...chats].sort(newestFirst) });
  }
  cases.sort((a, b) => newestFirst(a.chats[0], b.chats[0]));

  return { practice: [...practice].sort(newestFirst), cases, legacy: [...legacy].sort(newestFirst) };
}
