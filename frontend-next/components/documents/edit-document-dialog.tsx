"use client";

import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { showToast } from "@/components/ui/toaster";
import { useUpdateDocument } from "@/hooks/use-documents";
import { useCases } from "@/hooks/use-cases";
import { X, FileEdit } from "lucide-react";
import { APIError } from "@/lib/api/client";
import type { Document, DocumentType, DocumentUpdateInput } from "@/types";

interface EditDocumentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  document: Document | null;
}

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "contract", label: "Contract" },
  { value: "evidence", label: "Evidence" },
  { value: "correspondence", label: "Correspondence" },
  { value: "motion", label: "Motion" },
  { value: "other", label: "Other" },
];

export function EditDocumentDialog({
  isOpen,
  onClose,
  onSuccess,
  document,
}: EditDocumentDialogProps) {
  const updateDocument = useUpdateDocument();
  const { data: cases = [] } = useCases("all");

  const [selectedCaseId, setSelectedCaseId] = useState<number | null>(null);
  const [selectedDocType, setSelectedDocType] = useState<DocumentType>("other");
  const [documentDate, setDocumentDate] = useState<string>("");

  // Reset form when document changes or dialog opens
  useEffect(() => {
    if (document && isOpen) {
      setSelectedCaseId(document.case_id);
      const allowedTypes = new Set(DOCUMENT_TYPES.map((type) => type.value));
      const currentType = document.document_type;
      setSelectedDocType(
        currentType && allowedTypes.has(currentType) ? currentType : "other",
      );
      setDocumentDate(document.document_date || "");
    }
  }, [document, isOpen]);

  // Close on escape key
  useEffect(() => {
    if (typeof document === "undefined") return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!document) return;

    const data: DocumentUpdateInput = {
      case_id: selectedCaseId,
      document_type: selectedDocType,
      document_date: documentDate || null,
    };

    try {
      await updateDocument.mutateAsync({ id: document.id, data });
      showToast.success(
        "Document updated",
        "Document details have been updated successfully.",
      );
      onSuccess?.();
      onClose();
    } catch (err) {
      console.error("Failed to update document:", err);
      let message = "Failed to update document. Please try again.";

      if (err instanceof APIError && err.data && typeof err.data === "object") {
        const payload = err.data as Record<string, unknown>;

        if (Array.isArray(payload.case_id) && payload.case_id[0]) {
          message = String(payload.case_id[0]);
        } else if (
          Array.isArray(payload.document_type) &&
          payload.document_type[0]
        ) {
          message = String(payload.document_type[0]);
        }
      }

      showToast.error("Update failed", message);
    }
  };

  if (!isOpen || !document) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Dialog */}
      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-document-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-100 rounded-lg">
              <FileEdit className="h-5 w-5 text-blue-600" />
            </div>
            <h2
              id="edit-document-title"
              className="text-lg font-semibold text-gray-900"
            >
              Edit Document
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Document Name (read-only) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Document Name
            </label>
            <div className="px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg text-gray-700 text-sm">
              {document.filename}
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Document name cannot be changed
            </p>
          </div>

          {/* Case Selection */}
          <div>
            <label
              htmlFor="edit_case_id"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Associated Case
            </label>
            <Select
              id="edit_case_id"
              value={selectedCaseId?.toString() || ""}
              onChange={(e) =>
                setSelectedCaseId(
                  e.target.value ? Number(e.target.value) : null,
                )
              }
            >
              <option value="">No case selected</option>
              {cases.map((caseItem) => (
                <option key={caseItem.id} value={caseItem.id}>
                  {caseItem.case_number} - {caseItem.title}
                </option>
              ))}
            </Select>
            <p className="mt-1 text-xs text-gray-500">
              Link or unlink this document with a case (choose No case selected
              to unassign)
            </p>
          </div>

          {/* Document Type */}
          <div>
            <label
              htmlFor="edit_document_type"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Document Type
            </label>
            <Select
              id="edit_document_type"
              value={selectedDocType}
              onChange={(e) =>
                setSelectedDocType(e.target.value as DocumentType)
              }
            >
              {DOCUMENT_TYPES.map((type) => (
                <option key={type.value} value={type.value}>
                  {type.label}
                </option>
              ))}
            </Select>
            <p className="mt-1 text-xs text-gray-500">
              Allowed types: motion, evidence, contract, correspondence, other
            </p>
          </div>

          {/* Document Date */}
          <div>
            <label
              htmlFor="edit_document_date"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Document Date
            </label>
            <Input
              id="edit_document_date"
              type="date"
              value={documentDate}
              onChange={(e) => setDocumentDate(e.target.value)}
            />
            <p className="mt-1 text-xs text-gray-500">
              Optional: The date associated with this document
            </p>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={updateDocument.isPending}
            >
              {updateDocument.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
