import type { Document } from "@/types";

/**
 * Single source of truth for a document's displayed processing state,
 * derived from the latest background ProcessingJob when one exists and
 * falling back to the document's own processing_status for legacy rows.
 */

// Resolves to the three chip meanings case-intel-theme.css defines (see
// components/ui/badge.tsx) -- completed is the only "ok" state, everything
// still in flight (queued/processing/pending) reads as "awaiting", and
// failed is the one alert.
const STATUS_CHIP: Record<string, "ok" | "pending" | "alert" | "none"> = {
  completed: "ok",
  processing: "pending",
  queued: "pending",
  pending: "pending",
  failed: "alert",
};

export function getDocumentDisplayStatus(doc: Document): {
  key: string;
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
        className={`ci-chip ci-chip--${STATUS_CHIP[key] || "pending"} inline-flex items-center whitespace-nowrap`}
        title={document.job_error || undefined}
      >
        {label}
      </span>
      {document.ocr_applied && (
        // Not a status -- an attribute of the document (it had no
        // extractable text and was OCRed) -- so it stays neutral rather
        // than borrowing one of the three status colors.
        <span
          className="ci-chip ci-chip--none inline-flex items-center"
          title="This document had no extractable text and was OCRed"
        >
          OCR
        </span>
      )}
    </span>
  );
}
