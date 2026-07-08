"use client";

import { useEffect, useRef, useState } from "react";
import {
  Download,
  History,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  X,
} from "lucide-react";
import { conversationsApi, chatApi } from "@/lib/api/chat";
import { APIError } from "@/lib/api/client";
import { cn, formatDateTime, formatRelativeTime, truncate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type {
  Citation,
  ChatResponse,
  Conversation,
  ConversationExportFormat,
  Message,
} from "@/types";

interface ChatPanelProps {
  caseId: number;
  className?: string;
  onClose?: () => void;
}

interface PendingChatRequest {
  conversationId: number | null;
  isNewChat: boolean;
  optimisticMessageId: number;
  query: string;
}

const SOURCES_SECTION_RE = /(?:\r?\n){2,}(?:\*\*|__)?sources:(?:\*\*|__)?[\s\S]*$/i;

function stripEmbeddedSources(content: string): string {
  return content.replace(SOURCES_SECTION_RE, "").trim();
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof APIError) {
    const detail =
      typeof error.data === "object" &&
      error.data !== null &&
      "detail" in error.data
        ? String(error.data.detail)
        : null;
    return detail || `Request failed (${error.status}).`;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "Something went wrong while contacting the server.";
}

export function ChatPanel({ caseId, className, onClose }: ChatPanelProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [activeConversationId, setActiveConversationId] = useState<number | null>(
    null,
  );
  const [isDraftChat, setIsDraftChat] = useState(false);
  const [conversationError, setConversationError] = useState<string | null>(null);
  const [messagesError, setMessagesError] = useState<string | null>(null);
  const [sendError, setSendError] = useState<string | null>(null);
  const [lastFailedRequest, setLastFailedRequest] =
    useState<PendingChatRequest | null>(null);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportFormat, setExportFormat] =
    useState<ConversationExportFormat>("txt");
  const [sendStartedAt, setSendStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeConversation = conversations.find(
    (conversation) => conversation.id === activeConversationId,
  );
  const canSend =
    Boolean(inputValue.trim()) &&
    !isSending &&
    !isLoadingMessages &&
    (isDraftChat || activeConversationId !== null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isSending, isLoadingMessages]);

  useEffect(() => {
    setActiveConversationId(null);
    setIsDraftChat(false);
    setConversations([]);
    setMessages([]);
    setInputValue("");
    setSendError(null);
    setMessagesError(null);
    setLastFailedRequest(null);

    void loadConversations();
  }, [caseId]);

  useEffect(() => {
    if (!isSending || sendStartedAt === null) {
      setElapsedSeconds(0);
      return;
    }
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - sendStartedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isSending, sendStartedAt]);

  const loadConversations = async () => {
    setIsLoadingConversations(true);
    try {
      const response = await conversationsApi.list(caseId);
      setConversations(response);
      setConversationError(null);
    } catch (error) {
      setConversationError(extractErrorMessage(error));
    } finally {
      setIsLoadingConversations(false);
    }
  };

  const loadConversationMessages = async (conversationId: number) => {
    setIsLoadingMessages(true);
    try {
      const response = await conversationsApi.getMessages(conversationId);
      setMessages(response);
      setMessagesError(null);
    } catch (error) {
      setMessagesError(extractErrorMessage(error));
    } finally {
      setIsLoadingMessages(false);
    }
  };

  const handleSelectConversation = async (conversationId: number) => {
    setActiveConversationId(conversationId);
    setIsDraftChat(false);
    setSendError(null);
    setMessages([]);
    setLastFailedRequest(null);
    await loadConversationMessages(conversationId);
  };

  const startNewChat = () => {
    setActiveConversationId(null);
    setIsDraftChat(true);
    setMessages([]);
    setInputValue("");
    setMessagesError(null);
    setSendError(null);
    setLastFailedRequest(null);
  };

  const sendMessage = async (
    request: PendingChatRequest,
    reuseOptimisticMessage: boolean = false,
  ) => {
    setIsSending(true);
    setSendStartedAt(Date.now());
    setSendError(null);
    setLastFailedRequest(null);

    if (!reuseOptimisticMessage) {
      const userMessage: Message = {
        id: request.optimisticMessageId,
        role: "user",
        content: request.query,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);
    }

    try {
      const response: ChatResponse = await chatApi.send({
        query: request.query,
        case_id: caseId,
        conversation_id: request.conversationId || undefined,
      });

      const nextConversationId =
        response.conversation_id ?? request.conversationId;
      if (nextConversationId !== null) {
        setActiveConversationId(nextConversationId);
      }
      if (request.isNewChat && nextConversationId !== null) {
        setIsDraftChat(false);
      }

      let content = response.answer;
      if (response.requires_clarification && response.clarification_question) {
        content += `\n\n${response.clarification_question}`;
      }

      const aiMessage: Message = {
        id: response.message_id || Date.now() + 1,
        role: "assistant",
        content,
        created_at: new Date().toISOString(),
        citations: response.citations,
      };

      setMessages((prev) => [...prev, aiMessage]);
      await loadConversations();
    } catch (error) {
      setSendError(extractErrorMessage(error));
      setLastFailedRequest(request);
    } finally {
      setIsSending(false);
      setSendStartedAt(null);
    }
  };

  const handleSend = async () => {
    if (!canSend) return;
    const query = inputValue.trim();
    setInputValue("");
    await sendMessage(
      {
        query,
        conversationId: activeConversationId,
        isNewChat: isDraftChat,
        optimisticMessageId: Date.now(),
      },
      false,
    );
  };

  const handleRetry = async () => {
    if (!lastFailedRequest || isSending) return;
    await sendMessage(lastFailedRequest, true);
  };

  const handleExport = async () => {
    if (!activeConversationId) return;
    setIsExporting(true);
    try {
      const { blob, filename } = await conversationsApi.export(
        activeConversationId,
        exportFormat,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setSendError(extractErrorMessage(error));
    } finally {
      setIsExporting(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <div
      className={cn(
        "flex h-full min-w-0 border-l border-gray-200 bg-white shadow-2xl",
        className,
      )}
    >
      <aside className="hidden w-[250px] shrink-0 border-r border-gray-200 bg-gray-50 lg:flex lg:flex-col">
        <div className="border-b border-gray-200 px-4 py-4">
          <div className="mb-3 flex items-center gap-2">
            <History className="h-4 w-4 text-gray-500" />
            <h3 className="text-sm font-semibold text-gray-900">History</h3>
          </div>
          <Button
            variant="primary"
            size="sm"
            className="w-full"
            onClick={startNewChat}
          >
            <Plus className="h-4 w-4" />
            New Chat
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {isLoadingConversations ? (
            <SidebarStatus label="Loading conversations..." />
          ) : conversationError ? (
            <SidebarError
              message={conversationError}
              onRetry={() => void loadConversations()}
            />
          ) : conversations.length === 0 ? (
            <SidebarStatus label="No saved conversations yet." />
          ) : (
            <div className="space-y-2">
              {conversations.map((conversation) => {
                const isActive =
                  !isDraftChat && conversation.id === activeConversationId;
                return (
                  <button
                    key={conversation.id}
                    type="button"
                    onClick={() => void handleSelectConversation(conversation.id)}
                    className={cn(
                      "w-full rounded-xl border px-3 py-3 text-left transition-colors",
                      isActive
                        ? "border-blue-200 bg-blue-50"
                        : "border-transparent bg-white hover:border-gray-200 hover:bg-gray-100",
                    )}
                  >
                    <div className="mb-1 text-sm font-medium text-gray-900">
                      {conversation.title || "Conversation"}
                    </div>
                    <div className="mb-2 text-xs text-gray-500">
                      {conversation.last_message_at
                        ? formatRelativeTime(conversation.last_message_at)
                        : formatDateTime(conversation.started_at)}
                    </div>
                    <div className="text-xs leading-5 text-gray-600">
                      {truncate(conversation.preview || "No preview available.", 72)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-gray-200 bg-white px-4 py-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-5 w-5 text-blue-600" />
                <h2 className="font-semibold text-gray-900">AI Assistant</h2>
              </div>
              <p className="mt-1 text-sm text-gray-500">
                {isDraftChat
                  ? "New chat draft"
                  : activeConversation
                    ? activeConversation.title
                    : "Select a conversation or start a new one"}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                className="lg:hidden"
                onClick={startNewChat}
              >
                <Plus className="h-4 w-4" />
                New Chat
              </Button>
              <div className="hidden items-center gap-2 sm:flex">
                <Select
                  value={exportFormat}
                  onChange={(e) =>
                    setExportFormat(e.target.value as ConversationExportFormat)
                  }
                  className="h-8 w-[90px] py-1 text-xs"
                  disabled={!activeConversationId || isExporting}
                >
                  <option value="txt">TXT</option>
                  <option value="md">MD</option>
                  <option value="pdf">PDF</option>
                </Select>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleExport()}
                  disabled={!activeConversationId || isExporting}
                >
                  {isExporting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Export
                </Button>
              </div>
              {onClose && (
                <Button variant="ghost" size="sm" onClick={onClose}>
                  <X className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>

          {sendError && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <div className="font-medium">Request failed</div>
              <div className="mt-1">{sendError}</div>
              {lastFailedRequest && (
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-3"
                  onClick={() => void handleRetry()}
                  disabled={isSending}
                >
                  Retry Last Message
                </Button>
              )}
            </div>
          )}
        </div>

        <div className="flex-1 overflow-y-auto bg-gray-50 p-4">
          {isLoadingMessages ? (
            <CenteredStatus label="Loading conversation..." />
          ) : messagesError ? (
            <CenteredError
              message={messagesError}
              onRetry={
                activeConversationId
                  ? () => void loadConversationMessages(activeConversationId)
                  : undefined
              }
            />
          ) : messages.length === 0 ? (
            <EmptyChatState
              isDraftChat={isDraftChat}
              hasConversations={conversations.length > 0}
              onStartNewChat={startNewChat}
            />
          ) : (
            <div className="space-y-4">
              {messages.map((message) => (
                <MessageItem key={message.id} message={message} />
              ))}
              {isSending && <TypingIndicator elapsedSeconds={elapsedSeconds} />}
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <div className="border-t border-gray-200 bg-white p-4">
          {!isDraftChat && activeConversationId === null && (
            <div className="mb-3 rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-3 text-sm text-gray-600">
              Choose a previous conversation from history or click New Chat before
              sending a message.
            </div>
          )}

          <div className="flex gap-3">
            <Textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isDraftChat
                  ? "Ask a question to begin this new conversation..."
                  : activeConversationId
                    ? "Continue the conversation..."
                    : "Select a conversation or click New Chat..."
              }
              className="min-h-[84px] resize-none"
              disabled={
                isSending ||
                isLoadingMessages ||
                (!isDraftChat && activeConversationId === null)
              }
            />
            <Button
              onClick={() => void handleSend()}
              disabled={!canSend}
              variant="primary"
              className="self-end px-4"
            >
              {isSending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

interface MessageItemProps {
  message: Message;
}

function MessageItem({ message }: MessageItemProps) {
  const isUser = message.role === "user";
  const displayContent =
    message.citations && message.citations.length > 0
      ? stripEmbeddedSources(message.content)
      : message.content;

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[90%] rounded-2xl p-4 text-sm shadow-sm",
          isUser
            ? "bg-blue-600 text-white"
            : "border border-gray-200 bg-white text-gray-900",
        )}
      >
        <RenderedMessageContent content={displayContent} />

        {message.citations && message.citations.length > 0 && (
          <div className="mt-4 border-t border-gray-100 pt-3">
            <div className="mb-2 text-xs font-medium text-gray-600">
              Sources
            </div>
            <div className="space-y-1">
              {message.citations.map((citation) => (
                <CitationBadge key={citation.id} citation={citation} />
              ))}
            </div>
          </div>
        )}

        <div
          className={cn(
            "mt-3 text-xs",
            isUser ? "text-blue-100" : "text-gray-500",
          )}
        >
          {formatRelativeTime(message.created_at)}
        </div>
      </div>
    </div>
  );
}

function CitationBadge({ citation }: { citation: Citation }) {
  return (
    <div className="rounded-lg border bg-gray-100 px-2 py-1 text-xs text-gray-700">
      {citation.citation_text ||
        `${citation.source_type} ${citation.document_id}`}
    </div>
  );
}

function TypingIndicator({ elapsedSeconds }: { elapsedSeconds: number }) {
  return (
    <div className="flex justify-start">
      <div className="rounded-2xl border border-blue-100 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="flex space-x-1">
            <div className="h-2 w-2 animate-bounce rounded-full bg-blue-500" />
            <div
              className="h-2 w-2 animate-bounce rounded-full bg-blue-500"
              style={{ animationDelay: "0.1s" }}
            />
            <div
              className="h-2 w-2 animate-bounce rounded-full bg-blue-500"
              style={{ animationDelay: "0.2s" }}
            />
          </div>
          <div>
            <div className="text-sm font-medium text-gray-900">
              AI is working on your answer
            </div>
            <div className="text-xs text-gray-500">
              {elapsedSeconds > 0
                ? `${elapsedSeconds}s elapsed. Responses can take a little while.`
                : "Responses can take a little while depending on model load."}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function RenderedMessageContent({ content }: { content: string }) {
  const blocks = content.replace(/\r\n/g, "\n").split(/\n{2,}/).filter(Boolean);

  if (blocks.length === 0) {
    return <div className="whitespace-pre-wrap">(empty)</div>;
  }

  return (
    <div className="space-y-3 leading-6">
      {blocks.map((block, index) => {
        const lines = block.split("\n").filter(Boolean);
        const isList = lines.length > 0 && lines.every((line) => /^[-*]\s+/.test(line));

        if (isList) {
          return (
            <ul key={`${block}-${index}`} className="list-disc space-y-1 pl-5">
              {lines.map((line, lineIndex) => (
                <li key={`${line}-${lineIndex}`}>
                  {renderInlineFormatting(line.replace(/^[-*]\s+/, ""))}
                </li>
              ))}
            </ul>
          );
        }

        return (
          <p key={`${block}-${index}`} className="whitespace-pre-wrap">
            {renderInlineFormatting(block)}
          </p>
        );
      })}
    </div>
  );
}

function renderInlineFormatting(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
    }
    return <span key={`${part}-${index}`}>{part}</span>;
  });
}

function SidebarStatus({ label }: { label: string }) {
  return <div className="px-2 py-6 text-center text-sm text-gray-500">{label}</div>;
}

function SidebarError({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
      <div>{message}</div>
      <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

function CenteredStatus({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="text-sm text-gray-500">{label}</div>
    </div>
  );
}

function CenteredError({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="max-w-sm rounded-2xl border border-red-200 bg-white p-6 text-center shadow-sm">
        <div className="text-base font-semibold text-gray-900">Could not load chat</div>
        <div className="mt-2 text-sm text-gray-600">{message}</div>
        {onRetry && (
          <Button
            variant="secondary"
            size="sm"
            className="mt-4"
            onClick={onRetry}
          >
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}

function EmptyChatState({
  isDraftChat,
  hasConversations,
  onStartNewChat,
}: {
  isDraftChat: boolean;
  hasConversations: boolean;
  onStartNewChat: () => void;
}) {
  return (
    <div className="flex h-full items-center justify-center">
      <div className="max-w-md rounded-3xl border border-dashed border-gray-300 bg-white p-8 text-center shadow-sm">
        <MessageSquare className="mx-auto mb-4 h-12 w-12 text-gray-300" />
        <div className="text-lg font-semibold text-gray-900">
          {isDraftChat ? "New conversation ready" : "Pick up where you left off"}
        </div>
        <p className="mt-2 text-sm text-gray-500">
          {isDraftChat
            ? "Your next message will create a fresh conversation for this case."
            : hasConversations
              ? "Select a previous conversation from the history list or start a fresh chat."
              : "Start the first saved conversation for this case."}
        </p>
        {!isDraftChat && (
          <Button
            variant="primary"
            size="sm"
            className="mt-4"
            onClick={onStartNewChat}
          >
            <Plus className="h-4 w-4" />
            New Chat
          </Button>
        )}
      </div>
    </div>
  );
}
