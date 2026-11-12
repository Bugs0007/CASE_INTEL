"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useApproveDraft, useCreateOutput, useDownloadOutput } from "@/hooks/use-drafts";
import { describeDraftError, type DraftProblem } from "./errors";
import { ProblemNote } from "./problem-note";
import type { DraftDestination, DraftDetail, DraftOutput, DraftRevision } from "@/types/draft";

function formatTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
}

export function openItemsOf(revision: DraftRevision): string[] {
  return [...(revision.body.verification_items ?? []), ...(revision.missing_facts ?? [])];
}

interface ApprovalPanelProps {
  caseId: number;
  draft: DraftDetail;
  /** The current saved revision. */
  revision: DraftRevision;
  /** Unsaved edits exist, so approval is not possible. */
  dirty: boolean;
  /** An older version is on screen. */
  viewingOld: boolean;
}

export function ApprovalPanel({ caseId, draft, revision, dirty, viewingOld }: ApprovalPanelProps) {
  const [acknowledged, setAcknowledged] = useState(false);
  const [problem, setProblem] = useState<DraftProblem | null>(null);
  const [exportProblem, setExportProblem] = useState<string | null>(null);
  const approve = useApproveDraft(caseId, draft.id);
  const createOutput = useCreateOutput(caseId, draft.id);
  const download = useDownloadOutput();

  const openItems = openItemsOf(revision);
  const needsAck = openItems.length > 0;
  const approvedSummary = draft.revisions.find((r) => r.id === draft.approved_revision_id) ?? null;
  const currentIsApproved = revision.approved_at !== null && approvedSummary?.id === revision.id;
  const approvalIsOlder = approvedSummary !== null && approvedSummary.id !== revision.id;

  const canApprove = !dirty && !viewingOld && !currentIsApproved && (!needsAck || acknowledged);

  const onApprove = () => {
    setProblem(null);
    approve.mutate(
      { revision_id: revision.id, ...(needsAck ? { acknowledge_open_items: acknowledged } : {}) },
      { onError: (error) => setProblem(describeDraftError(error, "Could not approve this version.")) },
    );
  };

  const approvedId = draft.approved_revision_id;
  const outputsFor = (destination: DraftDestination): DraftOutput | undefined =>
    draft.outputs
      .filter((o) => o.revision_id === approvedId && o.destination === destination)
      .sort((a, b) => b.id - a.id)[0];

  const saveFile = (output: DraftOutput) => {
    setExportProblem(null);
    download.mutate(
      { outputId: output.id, filename: output.filename },
      { onError: (error) => setExportProblem(describeDraftError(error, "Could not download the file.").message) },
    );
  };

  const runOutput = (destination: DraftDestination) => {
    if (approvedId === null) return;
    setExportProblem(null);
    createOutput.mutate(
      { revision_id: approvedId, destination },
      {
        onSuccess: (output) => {
          if (destination === "docx" && output.status === "ready") saveFile(output);
        },
        onError: (error) =>
          setExportProblem(describeDraftError(error, "Could not create the output. Try again.").message),
      },
    );
  };

  const docx = outputsFor("docx");
  const note = outputsFor("case_note");

  return (
    <section aria-labelledby="approval-heading" className="space-y-3 rounded-lg border border-gray-200 p-3">
      <h3 id="approval-heading" className="text-sm font-semibold text-gray-900">
        Approval
      </h3>

      {approvedSummary && (
        <p className="text-sm text-gray-800" data-testid="approved-line">
          Approved {formatTime(approvedSummary.approved_at)}
          {approvalIsOlder ? ` (version ${approvedSummary.version})` : ""}
        </p>
      )}
      {approvalIsOlder && approvedSummary && (
        <p className="rounded-lg bg-amber-50 p-2 text-sm text-amber-900">
          {`The approval belongs to version ${approvedSummary.version}, not the latest version. Exports still come from version ${approvedSummary.version}. Approve the latest version to export it.`}
        </p>
      )}

      {!currentIsApproved && (
        <>
          {needsAck && (
            <label className="flex items-start gap-2 text-sm text-gray-800">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 shrink-0 focus-visible:ring-2 focus-visible:ring-primary"
                checked={acknowledged}
                onChange={(e) => setAcknowledged(e.target.checked)}
              />
              <span>I have checked the items above</span>
            </label>
          )}
          {dirty && <p className="text-xs text-gray-600">Save your edits as a new version before approving.</p>}
          <Button type="button" disabled={!canApprove || approve.isPending} onClick={onApprove}>
            Approve this version
          </Button>
          <ProblemNote problem={problem} />
        </>
      )}

      {approvedId !== null && (
        <div className="space-y-2 border-t border-gray-100 pt-3">
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              disabled={createOutput.isPending}
              onClick={() => (docx?.status === "ready" ? saveFile(docx) : runOutput("docx"))}
            >
              Export DOCX
            </Button>
            <Button
              type="button"
              variant="secondary"
              disabled={createOutput.isPending || note?.status === "ready"}
              onClick={() => runOutput("case_note")}
            >
              Save as case note
            </Button>
          </div>
          {docx?.status === "pending" && <p className="text-sm text-gray-600" role="status">Preparing the DOCX file.</p>}
          {docx?.status === "failed" && (
            <p className="text-sm text-destructive" role="alert">
              {docx.error || "The DOCX file could not be prepared."} Try exporting again.
            </p>
          )}
          {note?.status === "pending" && <p className="text-sm text-gray-600" role="status">Saving the note.</p>}
          {note?.status === "ready" && <p className="text-sm text-gray-800">Saved as a case note.</p>}
          {note?.status === "failed" && (
            <p className="text-sm text-destructive" role="alert">
              {note.error || "The note could not be saved."} Try again.
            </p>
          )}
          {exportProblem && (
            <p className="text-sm text-destructive" role="alert">
              {exportProblem}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
