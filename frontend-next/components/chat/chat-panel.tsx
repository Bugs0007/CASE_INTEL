"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageSquare, Send, RefreshCw } from "lucide-react";
import { cn, formatRelativeTime } from "@/lib/utils";
import type { Message, Citation } from "@/types";

interface ChatPanelProps {
  caseId: number;
  className?: string;
}

export function ChatPanel({ caseId, className }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now(),
      role: "user",
      content: inputValue,
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);

    try {
      // TODO: Implement actual API call
      // const response = await chatApi.send({
      //   query: inputValue,
      //   case_id: caseId,
      // });

      // Simulate AI response
      setTimeout(() => {
        const aiMessage: Message = {
          id: Date.now() + 1,
          role: "assistant",
          content:
            "I'm analyzing your case documents and legal precedents. Based on the information available, I can help you with legal research, document analysis, and case strategy development. What specific aspect of the case would you like me to focus on?",
          created_at: new Date().toISOString(),
          citations: [
            {
              id: 1,
              source_type: "document",
              document_id: 1,
              chunk_id: null,
              citation_text: "Contract Agreement Section 3.2",
              created_at: new Date().toISOString(),
            },
          ],
        };
        setMessages((prev) => [...prev, aiMessage]);
        setIsLoading(false);
      }, 2000);
    } catch (error) {
      console.error("Chat error:", error);
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const startNewChat = () => {
    setMessages([]);
  };

  return (
    <div
      className={cn(
        "flex flex-col h-full bg-gray-50 border-l border-gray-200",
        className,
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-white">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5 text-blue-600" />
          <h2 className="font-semibold text-gray-900">AI Assistant</h2>
        </div>
        <Button variant="ghost" size="sm" onClick={startNewChat}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <MessageSquare className="h-12 w-12 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-500 text-sm mb-2">
              Start a conversation with AI
            </p>
            <p className="text-xs text-gray-400">
              Ask questions about this case, documents, or legal research.
            </p>
          </div>
        )}

        {messages.map((message) => (
          <MessageItem key={message.id} message={message} />
        ))}

        {isLoading && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <Textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about this case..."
            className="min-h-[60px] resize-none"
            disabled={isLoading}
          />
          <Button
            onClick={handleSend}
            disabled={!inputValue.trim() || isLoading}
            variant="primary"
            className="px-4"
          >
            <Send className="h-4 w-4" />
          </Button>
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

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg p-3 text-sm",
          isUser
            ? "bg-blue-600 text-white"
            : "bg-white border border-gray-200 text-gray-900",
        )}
      >
        <div className="whitespace-pre-wrap">{message.content}</div>

        {/* Citations */}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-100">
            <div className="text-xs font-medium mb-2">📎 Sources:</div>
            <div className="space-y-1">
              {message.citations.map((citation) => (
                <CitationBadge key={citation.id} citation={citation} />
              ))}
            </div>
          </div>
        )}

        {/* Timestamp */}
        <div
          className={cn(
            "text-xs mt-2",
            isUser ? "text-blue-100" : "text-gray-500",
          )}
        >
          {formatRelativeTime(message.created_at)}
        </div>
      </div>
    </div>
  );
}

interface CitationBadgeProps {
  citation: Citation;
}

function CitationBadge({ citation }: CitationBadgeProps) {
  return (
    <div className="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded border">
      {citation.citation_text ||
        `${citation.source_type} ${citation.document_id}`}
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-lg p-3">
        <div className="flex items-center gap-1">
          <div className="flex space-x-1">
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
            <div
              className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
              style={{ animationDelay: "0.1s" }}
            />
            <div
              className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
              style={{ animationDelay: "0.2s" }}
            />
          </div>
          <span className="text-xs text-gray-500 ml-2">AI is thinking...</span>
        </div>
      </div>
    </div>
  );
}
