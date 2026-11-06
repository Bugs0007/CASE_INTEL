"use client";

import { useState } from "react";
import Link from "next/link";
import { Eye, Trash2, Play, Loader2, Pencil, MoreVertical } from "lucide-react";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { cn, formatDate, getFileIcon, staggerDelay } from "@/lib/utils";
import {
  DocumentStatusBadge,
  isDocumentActive,
} from "./document-status-badge";
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
}

const ACTION_BTN =
  "inline-flex items-center gap-1.5 h-11 md:h-8 px-3 rounded-md border border-gray-200 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

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
        <span className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-gray-100 text-lg" aria-hidden="true">
          {isViewing ? <Loader2 className="h-4 w-4 animate-spin" /> : getFileIcon(document.file_type)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="line-clamp-2 text-[14.5px] font-semibold leading-snug text-gray-900">{name}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-x-1.5 font-mono text-[11.5px] text-gray-500">
            <span>{document.case ? document.case.case_number : "No case"}</span>
            <span>·</span>
            <span>{formatDate(document.document_date || document.created_at, "MMM d, yyyy")}</span>
          </span>
          {document.case && <span className="mt-0.5 block truncate text-[12px] text-gray-500">{document.case.title}</span>}
          <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <DocumentStatusBadge document={document} />
            {document.document_type === "court_order" && <span className="ci-chip ci-chip--none">From eCourts</span>}
          </span>
          {document.ai_summary && (
            <span className="mt-1.5 line-clamp-2 block text-[12.5px] leading-snug text-gray-600">{document.ai_summary}</span>
          )}
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

function DesktopDocumentRow({
  document,
  onProcess,
  onDelete,
  onEdit,
  onView,
  isProcessing,
  isDeleting,
  isViewing,
}: DocumentRowProps) {
  const fileIcon = getFileIcon(document.file_type);
  // No Process/Retry button while a background job is queued or running.
  const canProcess =
    !isDocumentActive(document) &&
    (document.processing_status === "pending" ||
      document.processing_status === "failed");

  return (
    <div className="bg-white border border-gray-100 rounded-lg px-[18px] py-4 flex items-center gap-4 flex-wrap">
      <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center flex-shrink-0 text-lg">
        {fileIcon}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2.5 mb-0.5 flex-wrap">
          <button
            type="button"
            onClick={() => onView(document.id)}
            className="text-sm font-semibold text-gray-900 truncate hover:text-primary hover:underline text-left"
            title={`Open ${document.filename}`}
          >
            {document.display_name || document.filename}
          </button>
          {document.document_type === "court_order" ? (
            <span className="ci-chip ci-chip--none flex-shrink-0">
              From eCourts
            </span>
          ) : (
            <span className="text-[11px] text-gray-400 capitalize">
              {document.document_type}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2.5 text-xs text-gray-400 flex-wrap font-mono">
          {document.case ? (
            <Link href={`/cases/${document.case.id}`} className="font-semibold text-primary hover:text-primary-hover">
              {document.case.case_number}
            </Link>
          ) : (
            <span className="font-sans">No case</span>
          )}
          {document.case && (
            <>
              <span>·</span>
              <span className="truncate font-sans">{document.case.title}</span>
            </>
          )}
          <span>·</span>
          <span>{formatDate(document.document_date || document.created_at, "MMM d, yyyy")}</span>
        </div>
        {document.ai_summary && (
          <div className="text-[12.5px] text-gray-600 mt-1.5 leading-relaxed line-clamp-2">
            {document.ai_summary}
          </div>
        )}
      </div>

      <DocumentStatusBadge document={document} />

      <div className="flex items-center gap-1.5 flex-shrink-0">
        {canProcess && (
          <button className={ACTION_BTN} onClick={() => onProcess(document.id)} disabled={isProcessing}>
            {isProcessing ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            {isProcessing ? "Processing…" : document.processing_status === "failed" ? "Retry" : "Process"}
          </button>
        )}
        <button className={ACTION_BTN} onClick={() => onEdit(document)} title="Edit">
          <Pencil className="h-3.5 w-3.5" />
          Edit
        </button>
        <button
          className={ACTION_BTN}
          onClick={() => onView(document.id)}
          disabled={isViewing}
          title="View"
        >
          {isViewing ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Eye className="h-3.5 w-3.5" />
          )}
          View
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-11 md:h-8 px-3 rounded-md border border-status-alert-soft bg-white text-destructive text-xs font-semibold hover:bg-status-alert-soft disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          onClick={() => onDelete(document.id)}
          disabled={isDeleting}
          title="Delete"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </button>
      </div>
    </div>
  );
}
