"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { PageDialog } from "@/components/cases/compact/compact-card";
import { useDrafts } from "@/hooks/use-drafts";
import { BriefForm } from "./brief-form";
import { DraftPanel } from "./draft-panel";
import type { DraftStatus, DraftSubtype } from "@/types/draft";

const STATUS_LABEL: Record<DraftStatus, string> = {
  queued: "Queued",
  generating: "Writing",
  ready: "Ready",
  failed: "Failed",
};
const TYPE_LABEL: Record<DraftSubtype, string> = {
  status_memo: "Case status memo",
  personal_note: "Personal note",
};

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

interface DraftStudioProps {
  caseId: number;
  caseTitle: string;
  open: boolean;
  /** The selected draft. null shows the brief form. Kept in the URL by the caller. */
  draftId: number | null;
  onSelect: (draftId: number | null) => void;
  onClose: () => void;
}

export function DraftStudio({ caseId, caseTitle, open, draftId, onSelect, onClose }: DraftStudioProps) {
  const drafts = useDrafts(caseId, open);
  const returnFocus = useRef<HTMLElement | null>(null);
  const list = drafts.data ?? [];

  return (
    <PageDialog isOpen={open} onClose={onClose} title="Draft with assistant" returnFocusRef={returnFocus}>
      <div className="flex min-w-0 flex-col gap-5 md:flex-row">
        <nav aria-label="Drafts for this case" className="w-full shrink-0 space-y-2 md:w-60">
          <Button type="button" size="sm" variant={draftId === null ? "primary" : "secondary"} onClick={() => onSelect(null)}>
            New draft
          </Button>
          {drafts.isLoading ? (
            <p className="text-sm text-gray-500">Loading drafts</p>
          ) : drafts.isError ? (
            <div role="alert" className="text-sm text-destructive">
              Could not load drafts.{" "}
              <button type="button" className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" onClick={() => drafts.refetch()}>
                Retry
              </button>
            </div>
          ) : list.length === 0 ? (
            <p className="text-sm text-gray-500">No drafts for this case yet.</p>
          ) : (
            <ul className="space-y-1">
              {list.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-current={item.id === draftId ? "true" : undefined}
                    onClick={() => onSelect(item.id)}
                    className={`w-full rounded-lg border px-3 py-2 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                      item.id === draftId ? "border-primary bg-primary/10" : "border-gray-200 bg-surface"
                    }`}
                  >
                    <span className="block break-words font-medium text-gray-900">{item.title || "Untitled draft"}</span>
                    <span className="block text-xs text-gray-600">
                      {`${STATUS_LABEL[item.status]}, ${TYPE_LABEL[item.subtype]}`}
                    </span>
                    <span className="block text-xs text-gray-500">{formatTime(item.updated_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>

        <div className="min-w-0 flex-1">
          {draftId === null ? (
            <BriefForm key="new" caseId={caseId} caseTitle={caseTitle} onCreated={onSelect} />
          ) : (
            <DraftPanel key={draftId} caseId={caseId} draftId={draftId} />
          )}
        </div>
      </div>
    </PageDialog>
  );
}
