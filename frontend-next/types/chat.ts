export interface Citation {
  id: number;
  source_type: "document" | "email" | "chunk";
  document_id: number | null;
  chunk_id: number | null;
  citation_text: string | null;
  created_at: string;
}

export interface Message {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  citations?: Citation[];
  /** Practice chats only: sources on an assistant message, the stored
   * request marker on a user message. Read through lib/practice-history.ts. */
  references?: unknown[];
}

export type ConversationScope = "case" | "legacy_documents" | "practice";

export interface Conversation {
  id: number;
  case_id: number | null;
  case_title?: string | null;
  scope?: ConversationScope;
  title: string | null;
  started_at: string;
  last_message_at: string | null;
  preview?: string;
  message_count?: number;
  messages?: Message[];
}

export type ConversationExportFormat = "txt" | "md" | "pdf";

export interface ChatRequest {
  query: string;
  case_id?: number;
  conversation_id?: number;
}

export interface ChatResponse {
  answer: string;
  confidence: number;
  query_type: string;
  requires_clarification: boolean;
  clarification_question: string | null;
  message_id: number | null;
  conversation_id: number | null;
  citations: Citation[];
}
