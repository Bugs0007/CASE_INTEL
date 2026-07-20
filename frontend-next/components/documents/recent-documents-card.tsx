"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Collapsible } from "@/components/ui/collapsible";
import { Eye, FileText, Upload, Trash2, Play, Loader2 } from "lucide-react";
import { formatDate, getFileIcon } from "@/lib/utils";
import {
  DocumentStatusBadge,
  isDocumentActive,
} from "./document-status-badge";
import type { Document } from "@/types";

const DEFAULT_VISIBLE_COUNT = 5;

interface RecentDocumentsCardProps {
  documents: Document[];
  isLoading: boolean;
  onUploadClick: () => void;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onView: (id: number) => void;
  isProcessPending: boolean;
  processingDocId?: number;
  isDeletePending: boolean;
  isViewPending?: boolean;
  viewingDocId?: number;
}

export function RecentDocumentsCard({
  documents,
  isLoading,
  onUploadClick,
  onProcess,
  onDelete,
  onView,
  isProcessPending,
  processingDocId,
  isDeletePending,
  isViewPending,
  viewingDocId,
}: RecentDocumentsCardProps) {
  const [sectionOpen, setSectionOpen] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const hasMore = documents.length > DEFAULT_VISIBLE_COUNT;
  const visibleDocs = showAll ? documents : documents.slice(0, DEFAULT_VISIBLE_COUNT);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle>Case Documents{documents.length > 0 ? ` (${documents.length})` : ""}</CardTitle>
        <div className="flex items-center gap-2">
          <CollapseToggle isOpen={sectionOpen} onToggle={() => setSectionOpen((v) => !v)} />
          <Button variant="primary" size="sm" onClick={onUploadClick}>
            <Upload className="h-4 w-4" />
            Upload Document
          </Button>
        </div>
      </CardHeader>
      <Collapsible isOpen={sectionOpen}>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-gray-500">Loading documents...</div>
          ) : documents.length === 0 ? (
            <div className="text-center py-8">
              <FileText className="h-12 w-12 text-gray-300 mx-auto mb-3" />
              <div className="text-gray-500">No documents yet</div>
              <div className="text-sm text-gray-400">Upload a document to get started</div>
            </div>
          ) : (
            <div>
              <div
                className={
                  showAll
                    ? "max-h-[420px] overflow-y-auto pr-1 space-y-2"
                    : "space-y-2"
                }
              >
                {visibleDocs.map((doc) => (
                  <DocumentRow
                    key={doc.id}
                    doc={doc}
                    onProcess={onProcess}
                    onDelete={onDelete}
                    onView={onView}
                    isProcessPending={isProcessPending}
                    processingDocId={processingDocId}
                    isDeletePending={isDeletePending}
                    isThisDocViewing={isViewPending && viewingDocId === doc.id}
                  />
                ))}
              </div>
              {hasMore && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full mt-2"
                  onClick={() => setShowAll((v) => !v)}
                >
                  {showAll ? "Show less" : `Show all (${documents.length})`}
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Collapsible>
    </Card>
  );
}

interface DocumentRowProps {
  doc: Document;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onView: (id: number) => void;
  isProcessPending: boolean;
  processingDocId?: number;
  isDeletePending: boolean;
  isThisDocViewing?: boolean;
}

function DocumentRow({
  doc,
  onProcess,
  onDelete,
  onView,
  isProcessPending,
  processingDocId,
  isDeletePending,
  isThisDocViewing,
}: DocumentRowProps) {
  const fileIcon = getFileIcon(doc.file_type);
  const isThisDocProcessing = isProcessPending && processingDocId === doc.id;

  return (
    <div className="flex items-center justify-between p-3 border border-gray-100 rounded-lg hover:bg-gray-50 transition-colors">
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <span className="text-xl flex-shrink-0">{fileIcon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              onClick={() => onView(doc.id)}
              className="font-medium text-gray-900 truncate hover:text-primary hover:underline text-left"
              title="Open document"
            >
              {doc.filename}
            </button>
            {doc.document_type === "court_order" && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 flex-shrink-0">
                From eCourts
              </span>
            )}
          </div>
          <div className="text-xs text-gray-500">
            {doc.document_type} • {formatDate(doc.created_at, "MMM d, yyyy")}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2 ml-4 flex-wrap justify-end">
        {!isDocumentActive(doc) &&
          (doc.processing_status === "pending" || doc.processing_status === "failed") && (
          <Button
            variant="secondary"
            size="sm"
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
        <DocumentStatusBadge document={doc} />
        <Button
          variant="ghost"
          size="sm"
          className="p-1 h-11 w-11 md:h-8 md:w-8"
          onClick={() => onView(doc.id)}
          disabled={isThisDocViewing}
          title="View"
        >
          {isThisDocViewing ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Eye className="h-4 w-4 text-gray-600" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="p-1 h-11 w-11 md:h-8 md:w-8"
          onClick={() => onDelete(doc.id)}
          disabled={isDeletePending}
          title="Delete"
        >
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  );
}
