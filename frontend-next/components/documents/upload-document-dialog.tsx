"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { showToast } from "@/components/ui/toaster";
import { useUploadDocument } from "@/hooks/use-documents";
import { useCases } from "@/hooks/use-cases";
import { X, Upload, File, AlertCircle } from "lucide-react";
import { cn, formatFileSize } from "@/lib/utils";
import type { DocumentType } from "@/types";

interface UploadDocumentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  defaultCaseId?: number;
}

const DOCUMENT_TYPES: { value: DocumentType; label: string }[] = [
  { value: "contract", label: "Contract" },
  { value: "pleading", label: "Pleading" },
  { value: "evidence", label: "Evidence" },
  { value: "correspondence", label: "Correspondence" },
  { value: "brief", label: "Brief" },
  { value: "motion", label: "Motion" },
  { value: "order", label: "Order" },
  { value: "other", label: "Other" },
];

const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB
const ALLOWED_TYPES = [
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.ms-excel",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "text/plain",
  "message/rfc822",
  "application/vnd.ms-outlook",
];

const ALLOWED_EXTENSIONS = [
  ".pdf",
  ".doc",
  ".docx",
  ".xls",
  ".xlsx",
  ".txt",
  ".eml",
  ".msg",
];

export function UploadDocumentDialog({
  isOpen,
  onClose,
  onSuccess,
  defaultCaseId,
}: UploadDocumentDialogProps) {
  const uploadDocument = useUploadDocument();
  const { data: cases = [] } = useCases("all");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedCaseId, setSelectedCaseId] = useState<number | undefined>(
    defaultCaseId,
  );
  const [selectedDocType, setSelectedDocType] = useState<DocumentType>("other");
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetForm = useCallback(() => {
    setSelectedFile(null);
    setSelectedCaseId(defaultCaseId);
    setSelectedDocType("other");
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, [defaultCaseId]);

  useEffect(() => {
    if (!isOpen) {
      resetForm();
    }
  }, [isOpen, resetForm]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  const validateFile = (file: File): string | null => {
    // Check file size
    if (file.size > MAX_FILE_SIZE) {
      return `File size exceeds ${formatFileSize(MAX_FILE_SIZE)}. Please choose a smaller file.`;
    }

    // Check file type
    const extension = "." + file.name.split(".").pop()?.toLowerCase();
    const isValidType =
      ALLOWED_TYPES.includes(file.type) ||
      ALLOWED_EXTENSIONS.includes(extension);

    if (!isValidType) {
      return `File type not supported. Allowed types: ${ALLOWED_EXTENSIONS.join(", ")}`;
    }

    return null;
  };

  const handleFileSelect = (file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setSelectedFile(null);
      return;
    }

    setError(null);
    setSelectedFile(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!selectedFile) {
      setError("Please select a file to upload");
      return;
    }

    try {
      await uploadDocument.mutateAsync({
        file: selectedFile,
        case_id: selectedCaseId,
        document_type: selectedDocType,
      });
      showToast.success(
        "Document uploaded",
        `${selectedFile.name} has been uploaded successfully.`,
      );
      onSuccess?.();
      onClose();
    } catch (err) {
      console.error("Failed to upload document:", err);
      showToast.error(
        "Upload failed",
        "Failed to upload document. Please try again.",
      );
      setError("Failed to upload document. Please try again.");
    }
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const removeFile = () => {
    setSelectedFile(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  if (!isOpen) return null;

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
        aria-labelledby="upload-document-title"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-green-100 rounded-lg">
              <Upload className="h-5 w-5 text-green-600" />
            </div>
            <h2
              id="upload-document-title"
              className="text-lg font-semibold text-gray-900"
            >
              Upload Document
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
          {/* File Drop Zone */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Document File <span className="text-red-500">*</span>
            </label>

            <input
              ref={fileInputRef}
              type="file"
              onChange={handleFileChange}
              accept={ALLOWED_EXTENSIONS.join(",")}
              className="hidden"
              aria-label="Select file"
            />

            {!selectedFile ? (
              <div
                onClick={openFilePicker}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                className={cn(
                  "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
                  isDragging
                    ? "border-blue-500 bg-blue-50"
                    : "border-gray-300 hover:border-gray-400 hover:bg-gray-50",
                )}
              >
                <Upload className="h-10 w-10 text-gray-400 mx-auto mb-3" />
                <p className="text-sm text-gray-600 mb-1">
                  <span className="font-medium text-blue-600">
                    Click to upload
                  </span>{" "}
                  or drag and drop
                </p>
                <p className="text-xs text-gray-500">
                  PDF, DOC, DOCX, XLS, XLSX, TXT, EML, MSG (max{" "}
                  {formatFileSize(MAX_FILE_SIZE)})
                </p>
              </div>
            ) : (
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-blue-100 rounded-lg">
                    <File className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm font-medium text-gray-900 truncate max-w-[200px]">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-gray-500">
                      {formatFileSize(selectedFile.size)}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={removeFile}
                  className="p-1 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors"
                  aria-label="Remove file"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>

          {/* Case Selection */}
          <div>
            <label
              htmlFor="case_id"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Associated Case
            </label>
            <Select
              id="case_id"
              value={selectedCaseId?.toString() || ""}
              onChange={(e) =>
                setSelectedCaseId(
                  e.target.value ? Number(e.target.value) : undefined,
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
              Optionally associate this document with a case
            </p>
          </div>

          {/* Document Type */}
          <div>
            <label
              htmlFor="document_type"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              Document Type
            </label>
            <Select
              id="document_type"
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
          </div>

          {/* Error Message */}
          {error && (
            <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
              <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="primary"
              disabled={!selectedFile || uploadDocument.isPending}
            >
              {uploadDocument.isPending ? "Uploading..." : "Upload Document"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
