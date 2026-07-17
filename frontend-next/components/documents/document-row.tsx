import Link from "next/link";
import { Download, Trash2, Play, Loader2, Pencil } from "lucide-react";
import { formatDate, getFileIcon } from "@/lib/utils";
import type { Document } from "@/types";

interface DocumentRowProps {
  document: Document;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  isProcessing?: boolean;
  isDeleting?: boolean;
}

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-[#e9f7f1] text-[#146349]",
  processing: "bg-[#ebf3fb] text-[#2f6fb0]",
  pending: "bg-gray-100 text-[#4b5468]",
  failed: "bg-[#fdecec] text-[#b32e26]",
};

const ACTION_BTN =
  "inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-gray-200 bg-white text-gray-700 text-xs font-semibold hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors";

export function DocumentRow({
  document,
  onProcess,
  onDelete,
  onEdit,
  isProcessing,
  isDeleting,
}: DocumentRowProps) {
  const fileIcon = getFileIcon(document.file_type);
  const canProcess =
    document.processing_status === "pending" || document.processing_status === "failed";

  return (
    <div className="bg-white border border-gray-100 rounded-[10px] px-[18px] py-4 flex items-center gap-4 flex-wrap transition-colors hover:bg-gray-50/60">
      <div className="w-10 h-10 rounded-lg bg-[#eef1fb] flex items-center justify-center flex-shrink-0 text-lg">
        {fileIcon}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2.5 mb-0.5 flex-wrap">
          <span className="text-sm font-semibold text-gray-900 truncate">
            {document.filename}
          </span>
          <span className="text-[11px] text-gray-400 capitalize">
            {document.document_type}
          </span>
        </div>
        <div className="flex items-center gap-2.5 text-xs text-gray-400 flex-wrap">
          {document.case ? (
            <Link href={`/cases/${document.case.id}`} className="font-semibold text-primary hover:text-primary-hover">
              {document.case.case_number}
            </Link>
          ) : (
            <span>No case</span>
          )}
          {document.case && (
            <>
              <span>·</span>
              <span className="truncate">{document.case.title}</span>
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

      <span
        className={`text-xs font-semibold h-[22px] px-2.5 inline-flex items-center rounded-full flex-shrink-0 ${STATUS_STYLES[document.processing_status] || STATUS_STYLES.pending}`}
      >
        {document.processing_status}
      </span>

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
        <button className={ACTION_BTN} title="Download">
          <Download className="h-3.5 w-3.5" />
          Download
        </button>
        <button
          className="inline-flex items-center gap-1.5 h-8 px-3 rounded-md border border-[#fbdada] bg-white text-destructive text-xs font-semibold hover:bg-[#fdecec] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
