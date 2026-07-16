"use client";

import { useSearchParams } from "next/navigation";
import { MessageSquare } from "lucide-react";

/** Shown only when the Cases page is reached via the Dashboard's "Ask AI
 * Assistant" tile (?from=ai) -- chat is scoped per-case, so that tile sends
 * the user here to pick one first. Without this, landing on the Cases page
 * after clicking "Ask AI Assistant" looks like the tile is broken. */
export function AiAssistantHintBanner() {
  const searchParams = useSearchParams();
  if (searchParams.get("from") !== "ai") return null;

  return (
    <div className="mb-6 flex items-center gap-2 rounded-lg bg-orange-50 border border-orange-100 px-4 py-3 text-sm text-orange-800">
      <MessageSquare className="h-4 w-4 flex-shrink-0" />
      <span>Select a case to start chatting with the AI Assistant.</span>
    </div>
  );
}
