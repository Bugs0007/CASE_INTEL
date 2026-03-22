"use client";

import { useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { DocumentFilters } from "@/components/documents/document-filters";
import { DocumentTable } from "@/components/documents/document-table";
import {
  useDocuments,
  useProcessDocument,
  useDeleteDocument,
} from "@/hooks/use-documents";
import { Upload } from "lucide-react";
import type { DocumentType, ProcessingStatus } from "@/types";

export default function DocumentsPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCase, setSelectedCase] = useState<number | null>(null);
  const [selectedType, setSelectedType] = useState<DocumentType | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<ProcessingStatus | null>(
    null,
  );

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
          doc.file_name.toLowerCase().includes(query) ||
          doc.document_type.toLowerCase().includes(query) ||
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
    } catch (error) {
      console.error("Failed to process document:", error);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
      await deleteDocument.mutateAsync(id);
    } catch (error) {
      console.error("Failed to delete document:", error);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
          <p className="text-gray-600 mt-1">
            Manage and analyze all case documents
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => {
            // TODO: Open upload dialog
          }}
        >
          <Upload className="h-4 w-4" />
          Upload Document
        </Button>
      </div>

      {/* Filters */}
      <div className="mb-6">
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
    </div>
  );
}
