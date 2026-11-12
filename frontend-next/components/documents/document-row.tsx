"use client";

import { useState } from "react";
import Link from "next/link";
import { Eye, Trash2, Play, Loader2, Pencil, MoreVertical } from "lucide-react";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { cn, formatDate, formatFileSize, getFileIcon, staggerDelay } from "@/lib/utils";
import { DocumentActionsMenu } from "./list/document-actions-menu";
import { docDate, docName } from "./list/model";
import { DocumentStatusBadge, isDocumentActive } from "./document-status-badge";
import type { Document } from "@/types";

interface DocumentRowProps {
  document: Document;
  /** Position in the list, for the phone's stagger-in. */
  index?: number;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  onView: (id: number) => void;
  isProcessing?: boolean;
  isDeleting?: boolean;
  isViewing?: boolean;
  /** Desktop table: false when the rows sit under a case group header. */
  showCase?: boolean;
}

export function DocumentRow(props: DocumentRowProps) {
  const isMobile = useIsMobile();
  return isMobile ? <MobileDocumentRow {...props} /> : <DesktopDocumentRow {...props} />;
}

/** A phone: a card that opens the document when tapped; every other action
 * (process, edit, delete) is in the sheet behind the three dots. */
function MobileDocumentRow({
  document,
  index = 0,
  onProcess,
  onDelete,
  onEdit,
  onView,
  isProcessing,
  isDeleting,
  isViewing,
}: DocumentRowProps) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const canProcess =
    !isDocumentActive(document) &&
    (document.processing_status === "pending" || document.processing_status === "failed");
  const name = document.display_name || document.filename;
  const row = "flex h-14 w-full items-center gap-3 px-4 text-[15px] font-semibold text-gray-900 disabled:opacity-50";

  return (
    <div
      style={staggerDelay(index, 45, 10)}
      className="relative animate-rise-in rounded-[3px] border border-gray-100 bg-white motion-reduce:animate-none"
    >
      <button
        type="button"
        onClick={() => onView(document.id)}
        disabled={isViewing}
        aria-label={`Open ${name}`}
        className="flex w-full items-start gap-3 p-3 pr-14 text-left [--press-scale:0.985]"
      >
        <span
          className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100 text-lg"
          aria-hidden="true"
        >
          {isViewing ? <Loader2 className="h-4 w-4 animate-spin" /> : getFileIcon(document.file_type)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 text-[14.5px] font-semibold leading-snug text-gray-900">{name}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 font-mono text-[11.5px] text-gray-500">
            <span>{document.case ? document.case.case_number : "No case"}</span>
            <span>·</span>
            <span>{formatDate(docDate(document), "MMM d, yyyy")}</span>
          </span>
          {document.case && (
            <span className="mt-0.5 block truncate text-[12px] text-gray-500">{document.case.title}</span>
          )}
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {document.processing_status !== "completed" && <DocumentStatusBadge document={document} />}
            {document.document_type === "court_order" && <span className="ci-chip ci-chip--none">From eCourts</span>}
          </span>
        </span>
      </button>
      <button
        type="button"
        aria-label="Document actions"
        aria-haspopup="dialog"
        onClick={() => setSheetOpen(true)}
        className="absolute right-1 top-1 flex h-11 w-11 items-center justify-center rounded-full text-gray-500"
      >
        <MoreVertical className="h-4 w-4" />
      </button>
      <BottomSheet open={sheetOpen} onClose={() => setSheetOpen(false)} label="Document actions" title={name}>
        <ul className="py-1">
          <li>
            <button
              type="button"
              className={row}
              onClick={() => {
                setSheetOpen(false);
                onView(document.id);
              }}
            >
              <Eye className="h-5 w-5 text-gray-500" aria-hidden="true" /> View
            </button>
          </li>
          {canProcess && (
            <li>
              <button
                type="button"
                className={row}
                disabled={isProcessing}
                onClick={() => {
                  setSheetOpen(false);
                  onProcess(document.id);
                }}
              >
                <Play className="h-5 w-5 text-gray-500" aria-hidden="true" />
                {document.processing_status === "failed" ? "Retry processing" : "Process"}
              </button>
            </li>
          )}
          <li>
            <button
              type="button"
              className={row}
              onClick={() => {
                setSheetOpen(false);
                onEdit(document);
              }}
            >
              <Pencil className="h-5 w-5 text-gray-500" aria-hidden="true" /> Edit details
            </button>
          </li>
          <li>
            <button
              type="button"
              className={cn(row, "!text-destructive")}
              disabled={isDeleting}
              onClick={() => {
                setSheetOpen(false);
                onDelete(document.id);
              }}
            >
              <Trash2 className="h-5 w-5" aria-hidden="true" /> Delete
            </button>
          </li>
        </ul>
      </BottomSheet>
    </div>
  );
}

/** One desktop table row. Clicking anywhere on it opens the document; the
 * case link, Retry and the menu do their own thing. */
function DesktopDocumentRow({
  document,
  onProcess,
  onDelete,
  onEdit,
  onView,
  isProcessing,
  isViewing,
  showCase = true,
}: DocumentRowProps) {
  const name = docName(document);
  const isFailed = document.processing_status === "failed" && !isDocumentActive(document);
  const completed = document.processing_status === "completed" && !isDocumentActive(document);
  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <tr
      onClick={() => onView(document.id)}
      className="cursor-pointer border-t border-gray-100 hover:bg-[var(--ci-ink-08)]"
    >
      <td className="w-[40%] max-w-0 py-1.5 pl-3 pr-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-gray-100 text-sm"
            aria-hidden="true"
          >
            {isViewing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : getFileIcon(document.file_type)}
          </span>
          <button
            type="button"
            onClick={(e) => {
              stop(e);
              onView(document.id);
            }}
            title={`Open ${document.filename}`}
            className="min-w-0 truncate text-left text-[13.5px] font-semibold text-gray-900 hover:text-primary hover:underline"
          >
            {name}
          </button>
          {document.document_type === "court_order" ? (
            <span className="ci-chip ci-chip--none flex-shrink-0">From eCourts</span>
          ) : (
            document.document_type && (
              <span className="flex-shrink-0 text-[11px] capitalize text-gray-400">{document.document_type}</span>
            )
          )}
        </div>
      </td>
      {showCase && (
        <td className="w-[28%] max-w-0 px-2 py-1.5">
          {document.case ? (
            <Link
              href={`/cases/${document.case.id}`}
              onClick={stop}
              title={`${document.case.title} (${document.case.case_number})`}
              className="block min-w-0 hover:text-primary"
            >
              <span className="block truncate text-[13px] text-gray-800">{document.case.title}</span>
              <span className="block truncate font-mono text-[11px] text-gray-500">{document.case.case_number}</span>
            </Link>
          ) : (
            <span className="text-[13px] text-gray-400">No case</span>
          )}
        </td>
      )}
      <td className="whitespace-nowrap px-2 py-1.5 text-[13px] text-gray-700">
        {formatDate(docDate(document), "MMM d, yyyy")}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5 text-right font-mono text-[12px] text-gray-500">
        {formatFileSize(document.file_size)}
      </td>
      <td className="whitespace-nowrap px-2 py-1.5">
        <div className="flex items-center gap-1.5">
          {isFailed && (
            <button
              type="button"
              onClick={(e) => {
                stop(e);
                onProcess(document.id);
              }}
              disabled={isProcessing}
              className="inline-flex h-7 items-center gap-1 rounded-md border border-gray-200 bg-white px-2 text-xs font-semibold text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              {isProcessing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
              {isProcessing ? "Retrying…" : "Retry"}
            </button>
          )}
          {completed ? (
            <span
              role="img"
              aria-label="Processed"
              title="Processed"
              className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--ci-listed)]"
            />
          ) : (
            <DocumentStatusBadge document={document} />
          )}
        </div>
      </td>
      <td className="w-10 py-1 pr-2 text-right" onClick={stop}>
        <DocumentActionsMenu
          document={document}
          onProcess={onProcess}
          onDelete={onDelete}
          onEdit={onEdit}
          onView={onView}
        />
      </td>
    </tr>
  );
}
