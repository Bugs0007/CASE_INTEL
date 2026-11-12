"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useDraft, useDraftRevision, useRetryDraft, useSaveRevision } from "@/hooks/use-drafts";
import { ApprovalPanel } from "./approval-panel";
import { DraftEditor } from "./draft-editor";
import { describeDraftError, type DraftProblem } from "./errors";
import { ProblemNote } from "./problem-note";
import type { DraftBody, DraftRevision } from "@/types/draft";

function formatTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

function NoteList({ title, items, blocking }: { title: string; items: string[]; blocking: boolean }) {
  if (items.length === 0) return null;
  return (
    <section
      aria-label={title}
      className={`rounded-lg border p-3 text-sm ${blocking ? "border-amber-300 bg-amber-50" : "border-gray-200 bg-gray-50"}`}
    >
      <h3 className="font-semibold text-gray-900">{title}</h3>
      <ul className="mt-1 list-disc space-y-0.5 pl-5 text-gray-800">
        {items.map((item, index) => (
          <li key={index} className="break-words">
            {item}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function DraftPanel({ caseId, draftId }: { caseId: number; draftId: number }) {
  const query = useDraft(draftId);
  const draft = query.data;
  const save = useSaveRevision(caseId, draftId);
  const retry = useRetryDraft(caseId, draftId);

  const [edited, setEdited] = useState<DraftBody | null>(null);
  const [baseId, setBaseId] = useState<number | null>(null);
  const [saveProblem, setSaveProblem] = useState<DraftProblem | null>(null);
  const [retryProblem, setRetryProblem] = useState<DraftProblem | null>(null);
  const [version, setVersion] = useState<number | null>(null);

  const dirty = edited !== null;
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  const current = draft?.current_revision ?? null;
  const viewingOld = current !== null && version !== null && version !== current.version;
  const older = useDraftRevision(draftId, viewingOld ? version : null);

  if (query.isLoading) return <p className="text-sm text-gray-500" role="status">Loading draft</p>;
  if (query.isError || !draft) {
    return (
      <div role="alert" className="space-y-2 text-sm text-destructive">
        <p>Could not load this draft.</p>
        <Button size="sm" variant="secondary" onClick={() => query.refetch()}>
          Retry
        </Button>
      </div>
    );
  }

  if (draft.status === "queued" || draft.status === "generating") {
    return (
      <p className="text-sm text-gray-700" role="status">
        {draft.status === "queued" ? "Waiting to start the draft." : "Writing the draft."} This page updates by itself.
      </p>
    );
  }

  if (draft.status === "failed") {
    return (
      <div className="space-y-3">
        <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {draft.error || "The draft could not be written."}
        </div>
        <ProblemNote problem={retryProblem} />
        <Button
          type="button"
          disabled={retry.isPending}
          onClick={() => {
            setRetryProblem(null);
            retry.mutate(undefined, {
              onError: (error) => setRetryProblem(describeDraftError(error, "Could not retry the draft.")),
            });
          }}
        >
          Retry
        </Button>
      </div>
    );
  }

  if (!current) return <p className="text-sm text-gray-600">This draft has no content yet.</p>;

  const shown: DraftRevision | null = viewingOld ? (older.data ?? null) : current;
  const body: DraftBody | null = viewingOld ? (older.data?.body ?? null) : (edited ?? current.body);
  const approvedId = draft.approved_revision_id;

  const onChange = (next: DraftBody) => {
    if (edited === null) setBaseId(current.id);
    setEdited(next);
  };

  const onSave = () => {
    if (!edited) return;
    setSaveProblem(null);
    save.mutate(
      { expected_revision: baseId ?? current.id, body: edited },
      {
        onSuccess: () => {
          setEdited(null);
          setBaseId(null);
        },
        onError: (error) => setSaveProblem(describeDraftError(error, "Could not save this version.")),
      },
    );
  };

  const reloadLatest = async () => {
    const result = await query.refetch();
    setBaseId(result.data?.current_revision?.id ?? null);
    setSaveProblem(null);
  };

  const warnings = shown
    ? Array.from(new Set([...(shown.body.warnings ?? []), ...(shown.warnings ?? [])]))
    : [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="min-w-0 flex-1 break-words text-base font-semibold text-gray-900">
          {body?.title || "Untitled draft"}
        </h2>
        {dirty && !viewingOld && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-900" role="status">
            Unsaved changes
          </span>
        )}
      </div>

      <section aria-label="Version history">
        <h3 className="mb-1 text-sm font-semibold text-gray-900">Versions</h3>
        <ul className="flex flex-wrap gap-1.5">
          {[...draft.revisions].reverse().map((rev) => {
            const selected = (version ?? current.version) === rev.version;
            return (
              <li key={rev.id}>
                <button
                  type="button"
                  aria-pressed={selected}
                  onClick={() => setVersion(rev.version === current.version ? null : rev.version)}
                  className={`rounded-lg border px-2.5 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                    selected ? "border-primary bg-primary/10 font-semibold" : "border-gray-300 bg-surface"
                  }`}
                >
                  {`Version ${rev.version}, ${rev.source}, ${formatTime(rev.created_at)}`}
                  {rev.id === approvedId && (
                    <span className="ml-1 rounded bg-green-100 px-1.5 py-0.5 text-green-900">Approved</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </section>

      {viewingOld && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg bg-gray-100 p-2 text-sm" role="status">
          <span>{`Version ${version} is shown read only.`}</span>
          <Button type="button" size="sm" variant="secondary" onClick={() => setVersion(null)}>
            Back to latest
          </Button>
        </div>
      )}
      {viewingOld && older.isLoading && <p className="text-sm text-gray-500">Loading version</p>}
      {viewingOld && older.isError && (
        <div role="alert" className="text-sm text-destructive">
          Could not load that version.{" "}
          <button type="button" className="underline" onClick={() => older.refetch()}>
            Retry
          </button>
        </div>
      )}

      {shown && body && (
        <>
          <NoteList title="Items to verify" items={body.verification_items ?? []} blocking />
          <NoteList title="Missing facts" items={shown.missing_facts ?? []} blocking />
          <NoteList title="Warnings" items={warnings} blocking={false} />

          <DraftEditor body={body} evidence={shown.evidence} caseId={caseId} readOnly={viewingOld} onChange={onChange} />
        </>
      )}

      {saveProblem?.code === "stale_revision" ? (
        <div role="alert" className="space-y-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <p>{saveProblem.message}</p>
          <p>Your edits are kept here. Saving after a reload replaces the latest version with your text.</p>
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="secondary" onClick={reloadLatest}>
              Reload latest
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setSaveProblem(null)}>
              Keep editing
            </Button>
          </div>
        </div>
      ) : (
        <ProblemNote problem={saveProblem} />
      )}

      {!viewingOld && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled={!dirty || save.isPending} onClick={onSave}>
            Save as new version
          </Button>
          {dirty && (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setEdited(null);
                setBaseId(null);
                setSaveProblem(null);
              }}
            >
              Discard edits
            </Button>
          )}
        </div>
      )}

      <ApprovalPanel
        caseId={caseId}
        draft={draft}
        revision={current}
        dirty={dirty}
        viewingOld={viewingOld}
      />
    </div>
  );
}
