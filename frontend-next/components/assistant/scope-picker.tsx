"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { ScopeChoices } from "@/components/assistant/scope-choices";
import { useCase } from "@/hooks/use-cases";
import type { AssistantScope } from "@/providers/assistant-provider";

/** The name of what a chat is about. A case without a known title is looked up. */
export function useScopeLabel(scope: AssistantScope | null): string {
  const caseId = scope?.kind === "case" ? scope.caseId : 0;
  const known = scope?.kind === "case" ? scope.caseTitle : null;
  const lookup = useCase(caseId, caseId !== 0 && !known);
  if (scope === null) return "Choose a scope";
  if (scope.kind === "practice") return "Your practice";
  return known || lookup.data?.title || "This case";
}

/** "Your practice" or a case, with a panel to change it. Changing it starts a
 * new chat in the new scope. */
export function ScopePicker({
  scope,
  onChange,
}: {
  scope: AssistantScope | null;
  onChange: (scope: AssistantScope) => void;
}) {
  const [open, setOpen] = useState(false);
  const label = useScopeLabel(scope);
  const rootRef = useRef<HTMLDivElement>(null);

  // Esc closes the panel only, not the popover around it.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setOpen(false);
      rootRef.current?.querySelector("button")?.focus();
    }
    const node = rootRef.current;
    node?.addEventListener("keydown", onKeyDown);
    return () => node?.removeEventListener("keydown", onKeyDown);
  }, [open]);

  return (
    <div ref={rootRef} className="relative min-w-0 flex-1">
      <button
        type="button"
        aria-expanded={open}
        aria-label={`Scope: ${label}. Change scope`}
        onClick={() => setOpen((value) => !value)}
        className="flex h-11 w-full min-w-0 items-center gap-1.5 rounded-lg border border-gray-200 bg-surface px-2.5 text-left text-sm font-medium text-gray-900 hover:bg-gray-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-9"
      >
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <ChevronDown className="h-4 w-4 flex-shrink-0 text-gray-500" aria-hidden="true" />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-10 mt-1 w-[min(20rem,calc(100vw-2rem))] rounded-lg border border-gray-200 bg-surface p-2 shadow-lg">
          <ScopeChoices
            onPick={(next) => {
              setOpen(false);
              onChange(next);
            }}
          />
        </div>
      )}
    </div>
  );
}
