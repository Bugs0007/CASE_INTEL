"use client";

import Link from "next/link";
import { Loader2, Play } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn, formatDate, formatFileSize, getFileIcon, staggerDelay } from "@/lib/utils";
import { DocumentActionsMenu } from "./list/document-actions-menu";
import { docDate, docName } from "./list/model";
import { DocumentStatusBadge, isDocumentActive } from "./document-status-badge";
import type { Document } from "@/types";

export interface DocumentCardProps {
  document: Document;
  /** Position in the grid, for the stagger-in. */
  index?: number;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  onView: (id: number) => void;
  isProcessing?: boolean;
  isViewing?: boolean;
}

/** One document, in the same card chrome as a case. Clicking the card opens
 * the viewer; the case link, Retry and the menu do their own thing. */
export function DocumentCard({
  document,
  index = 0,
  onProcess,
  onDelete,
  onEdit,
  onView,
  isProcessing,
  isViewing,
}: DocumentCardProps) {
  const name = docName(document);
  const isFailed = document.processing_status === "failed" && !isDocumentActive(document);
  const completed = document.processing_status === "completed" && !isDocumentActive(document);
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <Card
      onClick={() => onView(document.id)}
      style={staggerDelay(index)}
      className={cn(
        "flex min-w-0 cursor-pointer flex-col p-[18px] transition-all hover:-translate-y-0.5 hover:shadow-md animate-fade-up motion-reduce:animate-none motion-reduce:hover:translate-y-0",
        isFailed && "border-status-pending",
      )}
    >
      <div className="mb-2.5 flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-gray-100 text-base"
            aria-hidden="true"
          >
            {isViewing ? <Loader2 className="h-4 w-4 animate-spin" /> : getFileIcon(document.file_type)}
          </span>
          {document.document_type === "court_order" ? (
            <span className="ci-chip ci-chip--none">From eCourts</span>
          ) : (
            document.document_type && <span className="ci-chip ci-chip--none capitalize">{document.document_type}</span>
          )}
          {!completed && <DocumentStatusBadge document={document} />}
        </div>
        <div onClick={stop} className="-mr-2 -mt-1 flex-shrink-0">
          <DocumentActionsMenu
            document={document}
            onProcess={onProcess}
            onDelete={onDelete}
            onEdit={onEdit}
            onView={onView}
          />
        </div>
      </div>

      <h3 className="mb-2 text-base font-semibold leading-snug text-gray-900">
        <button
          type="button"
          onClick={(e) => {
            stop(e);
            onView(document.id);
          }}
          title={`Open ${document.filename}`}
          className="line-clamp-2 break-words text-left hover:text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {name}
        </button>
      </h3>

      <div className="mb-3.5 min-w-0 text-meta text-gray-600">
        {document.case ? (
          <Link
            href={`/cases/${document.case.id}`}
            onClick={stop}
            title={`${document.case.title} (${document.case.case_number})`}
            className="block min-w-0 hover:text-primary"
          >
            <span className="block truncate">{document.case.title}</span>
            <span className="block truncate font-mono text-xs text-gray-400">{document.case.case_number}</span>
          </Link>
        ) : (
          <span className="text-gray-400">No case</span>
        )}
      </div>

      <div className="mt-auto flex items-center gap-3.5 border-t border-gray-100 pt-3 text-xs text-gray-400">
        <span>{formatDate(docDate(document), "MMM d, yyyy")}</span>
        <span className="font-mono">{formatFileSize(document.file_size)}</span>
        {isFailed && (
          <button
            type="button"
            onClick={(e) => {
              stop(e);
              onProcess(document.id);
            }}
            disabled={isProcessing}
            className="ml-auto inline-flex h-11 items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50 md:h-8"
          >
            {isProcessing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
            {isProcessing ? "Retrying…" : "Retry"}
          </button>
        )}
      </div>
    </Card>
  );
}
