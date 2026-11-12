"use client";

import { Button } from "@/components/ui/button";
import { CASE_DRAFTING_ENABLED } from "@/lib/feature-flags";
import { useCaseNotes, useDeleteCaseNote } from "@/hooks/use-drafts";

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

const SECTION = "rounded-xl border border-gray-200 bg-surface p-4";

/** Saved case notes. Shown whenever at least one exists, so notes stay
 * visible with drafting switched off; the loading, empty and error states
 * appear only with drafting on. */
export function CaseNotesSection({ caseId }: { caseId: number }) {
  const notes = useCaseNotes(caseId);
  const remove = useDeleteCaseNote(caseId);
  const list = notes.data ?? [];

  if (list.length === 0) {
    if (!CASE_DRAFTING_ENABLED) return null;
    if (notes.isLoading) {
      return (
        <section aria-label="Notes" className={SECTION}>
          <p className="text-sm text-gray-500">Loading notes</p>
        </section>
      );
    }
    if (notes.isError) {
      return (
        <section aria-labelledby="case-notes-heading" className={SECTION}>
          <h2 id="case-notes-heading" className="text-sm font-semibold text-gray-900">Notes</h2>
          <p className="mt-2 text-sm text-destructive">Could not load notes.</p>
          <Button size="sm" variant="secondary" className="mt-2" onClick={() => notes.refetch()}>
            Retry
          </Button>
        </section>
      );
    }
    return (
      <section aria-labelledby="case-notes-heading" className={SECTION}>
        <h2 id="case-notes-heading" className="text-sm font-semibold text-gray-900">Notes</h2>
        <p className="mt-2 text-sm text-gray-500">
          No notes yet. Approve a draft and save it as a case note to see it here.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="case-notes-heading" className={SECTION}>
      <h2 id="case-notes-heading" className="text-sm font-semibold text-gray-900">Notes</h2>
      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          Could not delete the note.
        </p>
      )}
      <ul className="mt-2 space-y-3">
        {list.map((note) => (
          <li key={note.id} className="min-w-0 rounded-lg border border-gray-100 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="break-words text-sm font-medium text-gray-900">{note.title}</p>
                <p className="text-xs text-gray-500">{formatDate(note.created_at)}</p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                aria-label={`Delete note ${note.title}`}
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm("Delete this note? This cannot be undone.")) remove.mutate(note.id);
                }}
              >
                Delete
              </Button>
            </div>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm text-gray-800">{note.body}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
