"use client";

import { useId, useState, type FormEvent } from "react";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";

/** One line above the practice block. Submitting hands the question to the
 * Case Bot, which opens in "Your practice" and answers there. */
export function PracticeAskBar({ onAsk }: { onAsk: (question: string) => void }) {
  const [draft, setDraft] = useState("");
  const inputId = useId();

  function submit(event: FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!question) return;
    onAsk(question);
    setDraft("");
  }

  return (
    <form onSubmit={submit} className="flex min-w-0 items-center gap-2">
      <label htmlFor={inputId} className="sr-only">
        Ask about your practice
      </label>
      <div className="relative min-w-0 flex-1">
        <Bot className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
        <input
          id={inputId}
          type="text"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask about your practice: hearings, deadlines, cases"
          className="h-11 w-full min-w-0 rounded-lg border border-gray-200 bg-surface pl-9 pr-3 text-sm placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-10"
        />
      </div>
      <Button type="submit" size="md" disabled={draft.trim() === ""}>
        Ask
      </Button>
    </form>
  );
}
