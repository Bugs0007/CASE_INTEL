"use client";

import { useEffect, useRef, useState } from "react";
import { Briefcase, User } from "lucide-react";
import { ScopeChoices } from "@/components/assistant/scope-choices";
import { useCase } from "@/hooks/use-cases";
import { cn } from "@/lib/utils";
import type { AssistantScope } from "@/providers/assistant-provider";

/** The name and number of what a chat is about. A case whose title or number
 * is not known yet is looked up. */
export function useScopeInfo(scope: AssistantScope | null): { label: string; number: string | null } {
  const caseId = scope?.kind === "case" ? scope.caseId : 0;
  const knownTitle = scope?.kind === "case" ? scope.caseTitle : null;
  const knownNumber = scope?.kind === "case" ? scope.caseNumber : null;
  const lookup = useCase(caseId, caseId !== 0 && !(knownTitle && knownNumber));
  if (scope === null) return { label: "Choose a scope", number: null };
  if (scope.kind === "practice") return { label: "Your practice", number: null };
  return {
    label: knownTitle || lookup.data?.title || "This case",
    number: knownNumber || lookup.data?.case_number || null,
  };
}

/** The name of what a chat is about. */
export function useScopeLabel(scope: AssistantScope | null): string {
  return useScopeInfo(scope).label;
}

/** Always-visible "Asking about" line by the input: the scope as a chip, with
 * a Change action that opens the chooser. Changing it starts a new chat in
 * the new scope. */
export function ScopeChip({
  scope,
  onChange,
  className,
}: {
  scope: AssistantScope | null;
  onChange: (scope: AssistantScope) => void;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const { label, number } = useScopeInfo(scope);
  const rootRef = useRef<HTMLDivElement>(null);
  const Icon = scope?.kind === "case" ? Briefcase : User;

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
    <div
      ref={rootRef}
      role="group"
      aria-label="Chat scope"
      className={cn("relative flex min-w-0 items-center gap-2", className)}
    >
      <span className="flex-shrink-0 text-xs text-gray-500">Asking about</span>
      <span
        title={number ? `${label} (${number})` : label}
        className="inline-flex min-w-0 max-w-full items-center gap-1.5 rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-xs font-semibold text-gray-900"
      >
        <Icon className="h-3.5 w-3.5 flex-shrink-0 text-primary" aria-hidden="true" />
        <span className="truncate">{label}</span>
        {number && <span className="flex-shrink-0 font-normal text-gray-500">{number}</span>}
      </span>
      <button
        type="button"
        aria-expanded={open}
        aria-label={`Scope: ${label}. Change scope`}
        onClick={() => setOpen((value) => !value)}
        className="flex h-11 flex-shrink-0 items-center rounded px-1.5 text-xs font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-8"
      >
        Change
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-10 mb-1 w-[min(22rem,calc(100vw-2rem))] rounded-lg border border-gray-200 bg-surface p-2 shadow-lg">
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
