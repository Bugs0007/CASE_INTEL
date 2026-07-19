import type { Document } from "@/types";

/**
 * Single source of truth for a document's displayed processing state,
 * derived from the latest background ProcessingJob when one exists and
 * falling back to the document's own processing_status for legacy rows.
 */

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-[#e9f7f1] text-[#146349]",
  processing: "bg-[#ebf3fb] text-[#2f6fb0]",
  queued: "bg-[#fdf4e3] text-[#8a6116]",
  pending: "bg-gray-100 text-[#4b5468]",
  failed: "bg-[#fdecec] text-[#b32e26]",
};

export function getDocumentDisplayStatus(doc: Document): {
  key: keyof typeof STATUS_STYLES;
  label: string;
} {
  if (doc.job_status === "queued") {
    return { key: "queued", label: "queued" };
  }
  if (doc.job_status === "running") {
    const total = doc.job_progress_total ?? 0;
    return {
      key: "processing",
      label:
        total > 0
          ? `Processing… ${doc.job_progress_current ?? 0}/${total}`
          : "Processing…",
    };
  }
  return { key: doc.processing_status, label: doc.processing_status };
}

/** True while a document still has background work pending/underway —
 * drives the documents list's refetchInterval polling. */
export function isDocumentActive(doc: Document): boolean {
  return (
    doc.job_status === "queued" ||
    doc.job_status === "running" ||
    doc.processing_status === "processing"
  );
}

export function DocumentStatusBadge({ document }: { document: Document }) {
  const { key, label } = getDocumentDisplayStatus(document);
  return (
    <span className="inline-flex items-center gap-1.5 flex-shrink-0">
      <span
        className={`text-xs font-semibold h-[22px] px-2.5 inline-flex items-center whitespace-nowrap rounded-full ${STATUS_STYLES[key] || STATUS_STYLES.pending}`}
        title={document.job_error || undefined}
      >
        {label}
      </span>
      {document.ocr_applied && (
        <span
          className="text-xs font-semibold h-[22px] px-2.5 inline-flex items-center rounded-full bg-[#f3ebfb] text-[#6b2fb0]"
          title="This document had no extractable text and was OCRed"
        >
          OCR
        </span>
      )}
    </span>
  );
}
