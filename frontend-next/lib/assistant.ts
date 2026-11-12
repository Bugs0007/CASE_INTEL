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
  caseNumber: string | null;
  chats: Conversation[];
}

export interface ChatGroups {
  practice: Conversation[];
  cases: CaseChatGroup[];
  legacy: Conversation[];
}

/** How many chats the sidebar's "Recent" shows. */
export const RECENT_CHAT_LIMIT = 8;

/** The newest chats across practice and case chats (older document chats are
 * read-only history and stay in their own group). */
export function recentChats(rows: Conversation[], limit = RECENT_CHAT_LIMIT): Conversation[] {
  return rows
    .filter((row) => row.scope !== "legacy_documents")
    .sort(newestFirst)
    .slice(0, limit);
}

/** The small label under a recent chat: its case's title, or "Practice". */
export function chatCaseLabel(chat: Pick<Conversation, "scope" | "case_id" | "case_title">): string {
  if (chat.scope === "practice") return "Practice";
  return chat.case_title || (chat.case_id !== null ? `Case ${chat.case_id}` : "Practice");
}

/** The sidebar's groups from the conversation lists. Practice and legacy
 * chats are newest first; each case is a group of its own, its chats newest
 * first, and the groups are ordered by their latest chat. The filter matches
 * chat titles, case titles and case numbers (`caseNumbers` maps case id to
 * number): a matching case keeps all its chats. */
export function groupConversations(
  rows: Conversation[],
  filter: string,
  caseNumbers: Record<number, string | null | undefined> = {},
): ChatGroups {
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
    const caseNumber = caseNumbers[caseId] ?? null;
    const caseMatches = matches(group.title) || (caseNumber !== null && matches(caseNumber));
    const chats = caseMatches ? group.chats : group.chats.filter((row) => matches(chatTitle(row)));
    if (chats.length > 0) cases.push({ caseId, title: group.title, caseNumber, chats: [...chats].sort(newestFirst) });
  }
  cases.sort((a, b) => newestFirst(a.chats[0], b.chats[0]));

  return { practice: [...practice].sort(newestFirst), cases, legacy: [...legacy].sort(newestFirst) };
}

export interface ChooserCase {
  id: number;
  title: string;
  case_number: string;
  client_name?: string | null;
  opposing_party?: string | null;
  petitioner_name?: string | null;
  respondent_name?: string | null;
  next_hearing_date?: string | null;
}

export interface ChooserSection {
  key: "page" | "recent" | "soon" | "all";
  label: string;
  cases: ChooserCase[];
}

/** Whether a case matches what was typed: title, case number or a party name. */
export function caseMatchesSearch(item: ChooserCase, needle: string): boolean {
  if (!needle) return true;
  const text = [item.title, item.case_number, item.client_name, item.opposing_party, item.petitioner_name, item.respondent_name]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return text.includes(needle);
}

/** The case chooser's sections, in order: this page's case, recent (the cases
 * with the newest chats), hearing soon (next hearing from `today` through
 * `soonUntil`, both YYYY-MM-DD), then every case A to Z. Empty sections are
 * left out. */
export function buildChooserSections({
  cases,
  filter,
  pageCaseId,
  recentCaseIds,
  today,
  soonUntil,
}: {
  cases: ChooserCase[];
  filter: string;
  pageCaseId: number | null;
  recentCaseIds: number[];
  today: string;
  soonUntil: string;
}): ChooserSection[] {
  const needle = filter.trim().toLowerCase();
  const found = cases.filter((item) => caseMatchesSearch(item, needle));
  const byId = new Map(found.map((item) => [item.id, item]));
  const sections: ChooserSection[] = [];

  const page = pageCaseId !== null ? byId.get(pageCaseId) : undefined;
  if (page) sections.push({ key: "page", label: "This page's case", cases: [page] });

  const recent = recentCaseIds
    .filter((id, index) => recentCaseIds.indexOf(id) === index && id !== pageCaseId)
    .map((id) => byId.get(id))
    .filter((item): item is ChooserCase => item !== undefined)
    .slice(0, 5);
  if (recent.length > 0) sections.push({ key: "recent", label: "Recent", cases: recent });

  // While searching, list each match once: this page's case and recent
  // cases first, then the rest A to Z.
  if (needle !== "") {
    const first = sections.flatMap((section) => section.cases);
    const firstIds = new Set(first.map((item) => item.id));
    const rest = found
      .filter((item) => !firstIds.has(item.id))
      .sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" }));
    const matches = [...first, ...rest];
    return matches.length > 0 ? [{ key: "all", label: "Matches", cases: matches }] : [];
  }

  const day = (item: ChooserCase) => (item.next_hearing_date ?? "").slice(0, 10);
  const soon = found
    .filter((item) => day(item) >= today && day(item) <= soonUntil && day(item) !== "")
    .sort((a, b) => day(a).localeCompare(day(b)));
  if (soon.length > 0) sections.push({ key: "soon", label: "Hearing soon", cases: soon });

  const all = [...found].sort((a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" }));
  if (all.length > 0) sections.push({ key: "all", label: "All cases", cases: all });
  return sections;
}
