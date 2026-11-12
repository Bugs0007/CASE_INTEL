"use client";

import Link from "next/link";
import { useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { apiErrorDetail } from "@/lib/api/client";
import { caseHref } from "./routes";

export interface CardOutcome {
  text: string;
  /** An internal link built from ids, such as "Open draft". */
  link?: { href: string; label: string };
}

export interface PracticeActionCardShellProps {
  /** Accessible name of the card, and its visible heading. */
  title: string;
  caseId: number;
  caseTitle: string;
  blockers: string[];
  /** First button, before the confirm step. */
  actionLabel: string;
  /** The question asked at the confirm step. */
  question: string;
  /** False while the form is incomplete: the first button stays disabled. */
  ready?: boolean;
  destructive?: boolean;
  /** Receives whether the fields may still be edited. */
  children?: (editable: boolean) => ReactNode;
  /** Runs once per confirm. A throw shows its message and allows another try. */
  run: () => Promise<CardOutcome>;
  onDismiss?: () => void;
}

/** The safety pattern every practice action card follows. Rendering (and a
 * replay of an old chat) calls nothing: the advocate presses the action
 * button, then Confirm. The confirm is held from its first click until it
 * settles, so a double click acts once. Blockers remove every way to act. */
export function PracticeActionCardShell({
  title,
  caseId,
  caseTitle,
  blockers,
  actionLabel,
  question,
  ready = true,
  destructive = false,
  children,
  run,
  onDismiss,
}: PracticeActionCardShellProps) {
  const [phase, setPhase] = useState<"edit" | "asking" | "working" | "done">("edit");
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<CardOutcome | null>(null);
  const locked = useRef(false);
  const blocked = blockers.length > 0;

  async function confirm() {
    if (locked.current) return;
    locked.current = true;
    setError(null);
    setPhase("working");
    try {
      const result = await run();
      setOutcome(result);
      setPhase("done");
    } catch (caught) {
      setError(apiErrorDetail(caught, "Try again in a moment."));
      setPhase("asking");
      locked.current = false;
    }
  }

  const editable = phase === "edit" && !blocked;
  return (
    <section aria-label={title} className="space-y-2 rounded-lg border border-gray-200 bg-surface p-3">
      <h4 className="text-sm font-semibold text-gray-900">{title}</h4>
      <p className="break-words text-sm text-gray-900">
        <span className="text-gray-500">Case </span>
        <Link href={caseHref(caseId)} className="text-primary hover:underline">
          {caseTitle || `Case ${caseId}`}
        </Link>
      </p>

      {children?.(editable)}

      {blocked && (
        <div role="alert" className="rounded-lg bg-amber-50 p-2 text-sm text-amber-900">
          <p className="font-medium">This cannot be done yet.</p>
          <ul className="list-disc pl-5">
            {blockers.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
        </div>
      )}

      {error && (
        <p role="alert" className="rounded-lg bg-red-50 p-2 text-sm text-red-800">
          {error}
        </p>
      )}

      {phase === "done" && outcome && (
        <p role="status" className="rounded-lg bg-green-50 p-2 text-sm text-green-900">
          {outcome.text}{" "}
          {outcome.link && (
            <Link href={outcome.link.href} className="font-medium underline">
              {outcome.link.label}
            </Link>
          )}
        </p>
      )}

      {!blocked && (phase === "asking" || phase === "working") && (
        <p role="group" aria-label="Confirm" className="text-sm text-gray-900">
          {question}
        </p>
      )}

      {phase !== "done" && (
        <div className="flex flex-wrap gap-2">
          {!blocked && phase === "edit" && (
            <Button
              type="button"
              size="sm"
              variant={destructive ? "danger" : "primary"}
              disabled={!ready}
              onClick={() => setPhase("asking")}
            >
              {actionLabel}
            </Button>
          )}
          {!blocked && (phase === "asking" || phase === "working") && (
            <>
              <Button
                type="button"
                size="sm"
                variant={destructive ? "danger" : "primary"}
                disabled={phase === "working"}
                onClick={confirm}
              >
                {error ? "Try again" : "Confirm"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                disabled={phase === "working"}
                onClick={() => {
                  setError(null);
                  setPhase("edit");
                }}
              >
                Cancel
              </Button>
            </>
          )}
          {onDismiss && (
            <Button type="button" variant="ghost" size="sm" disabled={phase === "working"} onClick={onDismiss}>
              Dismiss
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
