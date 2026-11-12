"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useDocuments } from "@/hooks/use-documents";
import { useCreateDraft } from "@/hooks/use-drafts";
import { describeDraftError, type DraftProblem } from "./errors";
import { ProblemNote } from "./problem-note";
import type { DraftLength, DraftSubtype, DraftTone } from "@/types/draft";

const MAX_INSTRUCTIONS = 2000;
const MAX_SOURCES = 20;
const SELECT_CLASS =
  "h-10 w-full rounded-lg border border-gray-200 bg-surface px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary";

export function BriefForm({
  caseId,
  caseTitle,
  onCreated,
}: {
  caseId: number;
  caseTitle: string;
  onCreated: (draftId: number) => void;
}) {
  const [subtype, setSubtype] = useState<DraftSubtype>("status_memo");
  const [instructions, setInstructions] = useState("");
  const [audience, setAudience] = useState("");
  const [tone, setTone] = useState<DraftTone>("neutral");
  const [length, setLength] = useState<DraftLength>("standard");
  const [sources, setSources] = useState<number[]>([]);
  const [problem, setProblem] = useState<DraftProblem | null>(null);
  // One id per form instance; it changes only when the brief changes, so a
  // retry of the same submit replays the same request.
  const requestId = useRef<string>(crypto.randomUUID());
  const touch = () => {
    requestId.current = crypto.randomUUID();
  };

  const documents = useDocuments({ case_id: caseId });
  const create = useCreateDraft(caseId);

  const toggleSource = (id: number) => {
    touch();
    setSources((current) => (current.includes(id) ? current.filter((d) => d !== id) : [...current, id]));
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setProblem(null);
    create.mutate(
      {
        case_id: caseId,
        subtype,
        instructions,
        audience,
        tone,
        length,
        source_document_ids: sources,
        client_request_id: requestId.current,
      },
      {
        onSuccess: (draft) => onCreated(draft.id),
        onError: (error) => setProblem(describeDraftError(error, "Could not start the draft. Try again.")),
      },
    );
  };

  const docs = documents.data ?? [];

  return (
    <form onSubmit={submit} className="space-y-4" aria-label="New draft brief">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Case</p>
        <p className="break-words text-sm text-gray-900" data-testid="brief-case">
          {caseTitle}
        </p>
      </div>

      <div>
        <label htmlFor="draft-type" className="mb-1 block text-sm font-medium text-gray-800">
          Type
        </label>
        <select
          id="draft-type"
          className={SELECT_CLASS}
          value={subtype}
          onChange={(e) => {
            touch();
            setSubtype(e.target.value as DraftSubtype);
          }}
        >
          <option value="status_memo">Case status memo</option>
          <option value="personal_note">Personal note</option>
          <option value="client_letter">Letter to the client</option>
          <option value="list_of_dates">List of dates</option>
        </select>
      </div>

      <div>
        <label htmlFor="draft-instructions" className="mb-1 block text-sm font-medium text-gray-800">
          Instructions
        </label>
        <Textarea
          id="draft-instructions"
          rows={5}
          maxLength={MAX_INSTRUCTIONS}
          value={instructions}
          onChange={(e) => {
            touch();
            setInstructions(e.target.value);
          }}
        />
        <p className="mt-1 text-xs text-gray-500" aria-live="polite">
          {instructions.length} / {MAX_INSTRUCTIONS}
        </p>
      </div>

      <div>
        <label htmlFor="draft-audience" className="mb-1 block text-sm font-medium text-gray-800">
          Audience
        </label>
        <Input
          id="draft-audience"
          maxLength={200}
          value={audience}
          onChange={(e) => {
            touch();
            setAudience(e.target.value);
          }}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="draft-tone" className="mb-1 block text-sm font-medium text-gray-800">
            Tone
          </label>
          <select
            id="draft-tone"
            className={SELECT_CLASS}
            value={tone}
            onChange={(e) => {
              touch();
              setTone(e.target.value as DraftTone);
            }}
          >
            <option value="neutral">Neutral</option>
            <option value="formal">Formal</option>
            <option value="plain">Plain</option>
          </select>
        </div>
        <div>
          <label htmlFor="draft-length" className="mb-1 block text-sm font-medium text-gray-800">
            Length
          </label>
          <select
            id="draft-length"
            className={SELECT_CLASS}
            value={length}
            onChange={(e) => {
              touch();
              setLength(e.target.value as DraftLength);
            }}
          >
            <option value="short">Short</option>
            <option value="standard">Standard</option>
            <option value="detailed">Detailed</option>
          </select>
        </div>
      </div>

      <fieldset className="min-w-0">
        <legend className="mb-1 text-sm font-medium text-gray-800">Sources</legend>
        {documents.isLoading ? (
          <p className="text-sm text-gray-500">Loading documents</p>
        ) : documents.isError ? (
          <p className="text-sm text-destructive">
            Could not load the case documents.{" "}
            <button
              type="button"
              className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              onClick={() => documents.refetch()}
            >
              Retry
            </button>
          </p>
        ) : docs.length === 0 ? (
          <p className="text-sm text-gray-500">This case has no documents.</p>
        ) : (
          <ul className="max-h-48 space-y-1 overflow-y-auto rounded-lg border border-gray-200 p-2">
            {docs.map((doc) => {
              const checked = sources.includes(doc.id);
              return (
                <li key={doc.id}>
                  <label className="flex min-h-8 items-start gap-2 text-sm text-gray-800">
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 shrink-0 focus-visible:ring-2 focus-visible:ring-primary"
                      checked={checked}
                      disabled={!checked && sources.length >= MAX_SOURCES}
                      onChange={() => toggleSource(doc.id)}
                    />
                    <span className="min-w-0 break-words">{doc.display_name || doc.filename}</span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        <p className="mt-1 text-xs text-gray-500">
          {sources.length === 0
            ? "No documents selected. The draft will use the recorded case details only."
            : `${sources.length} of ${MAX_SOURCES} documents selected.`}
        </p>
      </fieldset>

      <ProblemNote problem={problem} />

      <Button type="submit" disabled={create.isPending}>
        {create.isPending ? "Starting" : "Generate draft"}
      </Button>
    </form>
  );
}
