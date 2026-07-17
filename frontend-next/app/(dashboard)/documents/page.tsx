"use client";

import { useState, useMemo } from "react";
import { DocumentFilters } from "@/components/documents/document-filters";
import { DocumentTable } from "@/components/documents/document-table";
import { EditDocumentDialog } from "@/components/documents/edit-document-dialog";
import { showToast } from "@/components/ui/toaster";
import {
  useDocuments,
  useProcessDocument,
  useDeleteDocument,
} from "@/hooks/use-documents";
import { useDialogs } from "@/providers/dialog-provider";
import { Upload } from "lucide-react";
import type { Document, DocumentType, ProcessingStatus } from "@/types";

export default function DocumentsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCase, setSelectedCase] = useState<number | null>(null);
  const [selectedType, setSelectedType] = useState<DocumentType | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<ProcessingStatus | null>(
    null,
  );
  const [editingDocument, setEditingDocument] = useState<Document | null>(null);
  const { openUploadDocument } = useDialogs();

  const { data: documents = [], isLoading } = useDocuments();
  const processDocument = useProcessDocument();
  const deleteDocument = useDeleteDocument();

  // Filter documents
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      // Search filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const matchesSearch =
          doc.filename?.toLowerCase().includes(query) ||
          doc.document_type?.toLowerCase().includes(query) ||
          doc.case?.title.toLowerCase().includes(query) ||
          doc.case?.case_number.toLowerCase().includes(query);
        if (!matchesSearch) return false;
      }

      // Case filter
      if (selectedCase && doc.case?.id !== selectedCase) {
        return false;
      }

      // Type filter
      if (selectedType && doc.document_type !== selectedType) {
        return false;
      }

      // Status filter
      if (selectedStatus && doc.processing_status !== selectedStatus) {
        return false;
      }

      return true;
    });
  }, [documents, searchQuery, selectedCase, selectedType, selectedStatus]);

  const handleProcess = async (id: number) => {
    try {
      await processDocument.mutateAsync(id);
      showToast.success(
        "Processing started",
        "Document is being analyzed by AI.",
      );
    } catch (error) {
      console.error("Failed to process document:", error);
      showToast.error(
        "Processing failed",
        "Could not start document processing.",
      );
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
      await deleteDocument.mutateAsync(id);
      showToast.success("Document deleted", "The document has been removed.");
    } catch (error) {
      console.error("Failed to delete document:", error);
      showToast.error("Delete failed", "Could not delete the document.");
    }
  };

  const handleEdit = (document: Document) => {
    setEditingDocument(document);
  };

  return (
    <div className="px-7 pt-7 pb-[60px] max-w-[1240px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-[22px] flex-wrap gap-3">
        <div>
          <h1 className="text-page-title text-gray-900 mb-1.5">Documents</h1>
          <p className="text-sm text-gray-600">
            {filteredDocuments.length} documents across all cases
          </p>
        </div>
        <button
          onClick={openUploadDocument}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-lg border-none bg-primary text-white text-sm font-semibold hover:bg-primary-hover transition-colors"
        >
          <Upload className="h-4 w-4" />
          Upload Document
        </button>
      </div>

      {/* Filters */}
      <div className="mb-5">
        <DocumentFilters
          onSearchChange={setSearchQuery}
          onCaseChange={setSelectedCase}
          onTypeChange={setSelectedType}
          onStatusChange={setSelectedStatus}
        />
      </div>

      {/* Documents Table */}
      <DocumentTable
        documents={filteredDocuments}
        isLoading={isLoading}
        onProcess={handleProcess}
        onDelete={handleDelete}
        onEdit={handleEdit}
        processingId={processDocument.variables}
        deletingId={deleteDocument.variables}
      />

      {/* Results Count */}
      {!isLoading && (
        <div className="mt-6 text-center text-sm text-gray-500">
          Showing {filteredDocuments.length}{" "}
          {filteredDocuments.length === 1 ? "document" : "documents"}
          {searchQuery && ` matching "${searchQuery}"`}
          {selectedCase && " for selected case"}
          {selectedType && ` of type "${selectedType}"`}
          {selectedStatus && ` with status "${selectedStatus}"`}
        </div>
      )}

      {/* Edit Document Dialog */}
      <EditDocumentDialog
        isOpen={!!editingDocument}
        document={editingDocument}
        onClose={() => setEditingDocument(null)}
      />
    </div>
  );
}
