"use client";

import { useId, useState } from "react";
import { Briefcase, Search, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCases } from "@/hooks/use-cases";
import { PORTFOLIO_BOT_ENABLED } from "@/lib/feature-flags";
import { cn } from "@/lib/utils";
import type { AssistantScope } from "@/providers/assistant-provider";

/** A searchable list of the advocate's cases. */
export function CaseChooser({
  onPick,
  onCancel,
}: {
  onPick: (scope: Extract<AssistantScope, { kind: "case" }>) => void;
  onCancel?: () => void;
}) {
  const cases = useCases();
  const [filter, setFilter] = useState("");
  const inputId = useId();
  const needle = filter.trim().toLowerCase();
  const shown = (cases.data ?? []).filter(
    (item) => !needle || `${item.title} ${item.case_number}`.toLowerCase().includes(needle),
  );

  return (
    <div className="space-y-2">
      <label htmlFor={inputId} className="sr-only">
        Search your cases
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
        <input
          id={inputId}
          type="search"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Search your cases"
          className="h-11 w-full rounded-lg border border-gray-200 bg-surface pl-8 pr-3 text-sm placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-9"
        />
      </div>
      {cases.isLoading ? (
        <p role="status" className="px-1 py-3 text-sm text-gray-500">
          Loading your cases.
        </p>
      ) : cases.isError ? (
        <div role="alert" className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
          <p className="text-sm text-red-800">Your cases could not be loaded.</p>
          <Button type="button" variant="secondary" size="sm" onClick={() => cases.refetch()}>
            Try again
          </Button>
        </div>
      ) : shown.length === 0 ? (
        <p className="px-1 py-3 text-sm text-gray-500">{needle ? "No case matches that search." : "You have no cases yet."}</p>
      ) : (
        <ul aria-label="Your cases" className="max-h-64 overflow-y-auto">
          {shown.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => onPick({ kind: "case", caseId: item.id, caseTitle: item.title })}
                className="flex min-h-[44px] w-full flex-col items-start rounded-lg px-2 py-1.5 text-left hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <span className="w-full break-words text-sm font-medium text-gray-900">{item.title}</span>
                <span className="w-full break-words text-xs text-gray-500">{item.case_number}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {onCancel && (
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Back
        </Button>
      )}
    </div>
  );
}

/** The two things a chat can be about: the whole practice (when it is
 * switched on) or one case, picked from the chooser. */
export function ScopeChoices({
  onPick,
  className,
}: {
  onPick: (scope: AssistantScope) => void;
  className?: string;
}) {
  const [choosingCase, setChoosingCase] = useState(false);
  if (choosingCase) {
    return (
      <div className={className}>
        <CaseChooser onPick={onPick} onCancel={() => setChoosingCase(false)} />
      </div>
    );
  }
  const optionClass =
    "flex min-h-[44px] w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm text-gray-900 hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";
  return (
    <ul className={cn("space-y-0.5", className)} aria-label="Choose what to ask about">
      {PORTFOLIO_BOT_ENABLED && (
        <li>
          <button type="button" className={optionClass} onClick={() => onPick({ kind: "practice" })}>
            <User className="h-4 w-4 text-gray-500" aria-hidden="true" />
            Your practice
          </button>
        </li>
      )}
      <li>
        <button type="button" className={optionClass} onClick={() => setChoosingCase(true)}>
          <Briefcase className="h-4 w-4 text-gray-500" aria-hidden="true" />
          A case...
        </button>
      </li>
    </ul>
  );
}
