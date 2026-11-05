"use client";

import { Button } from "@/components/ui/button";
import { ExpandableCard } from "@/components/ui/expandable-card";
import { Eye, FilePlus2, FileText, Upload, Trash2, Play, Loader2 } from "lucide-react";
import { formatDate, getFileIcon } from "@/lib/utils";
import {
  latestOrderDocument,
  matchesQuery,
  previewDocuments,
  sortDocuments,
} from "@/lib/case-previews";
import {
  DocumentStatusBadge,
  isDocumentActive,
} from "./document-status-badge";
import type { Document } from "@/types";

interface RecentDocumentsCardProps {
  documents: Document[];
  isLoading: boolean;
  onUploadClick: () => void;
  /** Opens the template generator (vakalatnama etc.). Omitted = no button. */
  onGenerateClick?: () => void;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  /** Opens the document in the viewer. */
  onView: (id: number) => void;
  isProcessPending: boolean;
  processingDocId?: number;
  isDeletePending: boolean;
}

/** The case's documents: the latest order pinned first, then the newest
 * uploads. The expanded view lists every document. */
export function RecentDocumentsCard({
  documents,
  isLoading,
  onUploadClick,
  onGenerateClick,
  onProcess,
  onDelete,
  onView,
  isProcessPending,
  processingDocId,
  isDeletePending,
}: RecentDocumentsCardProps) {
  const previewed = previewDocuments(documents);
  const pinnedId = latestOrderDocument(documents)?.id;

  return (
    <ExpandableCard
      title="Documents"
      count={documents.length}
      actions={
        <>
          {onGenerateClick && (
            <Button variant="secondary" size="sm" onClick={onGenerateClick}>
              <FilePlus2 className="h-4 w-4" />
              Generate
            </Button>
          )}
          <Button variant="primary" size="sm" onClick={onUploadClick}>
            <Upload className="h-4 w-4" />
            Upload
          </Button>
        </>
      }
      viewAll={{ total: documents.length, shown: previewed.length }}
      expandable={documents.length > 0}
    >
      {({ expanded, query }) => {
        if (isLoading) {
          return <div className="text-center py-8 text-gray-500">Loading documents...</div>;
        }
        if (documents.length === 0) {
          return (
            <div className="text-center py-8">
              <FileText className="h-12 w-12 text-gray-300 mx-auto mb-3" />
              <div className="text-gray-500">No documents yet</div>
              <div className="text-sm text-gray-400">Upload a document to get started</div>
            </div>
          );
        }

        const visible = expanded
          ? sortDocuments(documents).filter((doc) =>
              matchesQuery(query, doc.display_name, doc.filename, doc.document_type),
            )
          : previewed;
        if (visible.length === 0) {
          return <p className="text-sm text-gray-500 py-2">No documents match.</p>;
        }

        return (
          <div className="space-y-2">
            {visible.map((doc) => (
              <DocumentRow
                key={doc.id}
                doc={doc}
                isLatestOrder={doc.id === pinnedId}
                onProcess={onProcess}
                onDelete={onDelete}
                onView={onView}
                isProcessPending={isProcessPending}
                processingDocId={processingDocId}
                isDeletePending={isDeletePending}
              />
            ))}
          </div>
        );
      }}
    </ExpandableCard>
  );
}

interface DocumentRowProps {
  doc: Document;
  isLatestOrder: boolean;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onView: (id: number) => void;
  isProcessPending: boolean;
  processingDocId?: number;
  isDeletePending: boolean;
}

function DocumentRow({
  doc,
  isLatestOrder,
  onProcess,
  onDelete,
  onView,
  isProcessPending,
  processingDocId,
  isDeletePending,
}: DocumentRowProps) {
  const fileIcon = getFileIcon(doc.file_type);
  const isThisDocProcessing = isProcessPending && processingDocId === doc.id;
  const canProcess =
    !isDocumentActive(doc) &&
    (doc.processing_status === "pending" || doc.processing_status === "failed");

  return (
    <div className="p-3 border border-gray-100 rounded-lg">
      <div className="flex items-start gap-3">
        <span className="text-xl flex-shrink-0">{fileIcon}</span>
        <div className="flex-1 min-w-0">
          <button
            type="button"
            onClick={() => onView(doc.id)}
            className="block max-w-full font-medium text-gray-900 truncate hover:text-primary hover:underline text-left"
            title={`Open ${doc.filename}`}
          >
            {doc.display_name || doc.filename}
          </button>
          <div className="mt-0.5 flex items-center gap-2 flex-wrap">
            <span className="text-xs font-mono text-gray-500">
              {doc.document_type} • {formatDate(doc.created_at, "MMM d, yyyy")}
            </span>
            {isLatestOrder && <span className="ci-chip ci-chip--ok">Latest order</span>}
            {doc.document_type === "court_order" && (
              <span className="ci-chip ci-chip--none">From eCourts</span>
            )}
            <DocumentStatusBadge document={doc} />
          </div>
          {canProcess && (
            <Button
              variant="secondary"
              size="sm"
              className="mt-2"
              onClick={() => onProcess(doc.id)}
              disabled={isProcessPending}
            >
              {isThisDocProcessing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {isThisDocProcessing
                ? "Processing..."
                : doc.processing_status === "failed"
                  ? "Retry"
                  : "Process"}
            </Button>
          )}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          <Button
            variant="ghost"
            size="sm"
            className="p-1 h-11 w-11 md:h-8 md:w-8"
            onClick={() => onView(doc.id)}
            title="View"
            aria-label={`View ${doc.display_name || doc.filename}`}
          >
            <Eye className="h-4 w-4 text-gray-600" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="p-1 h-11 w-11 md:h-8 md:w-8"
            onClick={() => onDelete(doc.id)}
            disabled={isDeletePending}
            title="Delete"
            aria-label={`Delete ${doc.display_name || doc.filename}`}
          >
            <Trash2 className="h-4 w-4 text-destructive" />
          </Button>
        </div>
      </div>
    </div>
  );
}
