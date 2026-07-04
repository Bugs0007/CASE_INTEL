"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useCase } from "@/hooks/use-cases";
import { useDocuments } from "@/hooks/use-documents";
import { useHearings } from "@/hooks/use-hearings";
import { CaseDetailHeader } from "@/components/cases/case-detail-header";
import { CaseOverview } from "@/components/cases/case-overview";
import { HearingsList } from "@/components/hearings/hearings-list";
import { ChatPanel } from "@/components/chat/chat-panel";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FileText, Upload, Trash2, Play, Loader2 } from "lucide-react";
import { formatDate, getFileIcon } from "@/lib/utils";
import { showToast } from "@/components/ui/toaster";
import { useProcessDocument, useDeleteDocument } from "@/hooks/use-documents";

export default function CaseDetailPage() {
  const params = useParams();
  const caseId = Number(params.id);
  const [showChat, setShowChat] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);

  const { data: caseItem, isLoading: caseLoading } = useCase(caseId);
  const { data: documents = [], isLoading: docsLoading } = useDocuments({
    case_id: caseId,
  });
  const { data: hearings = [], isLoading: hearingsLoading } = useHearings({
    case_id: caseId,
  });

  const processDocument = useProcessDocument();
  const deleteDocument = useDeleteDocument();

  if (caseLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="text-lg text-gray-500">Loading case details...</div>
      </div>
    );
  }

  if (!caseItem) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div>
          <div className="text-xl font-semibold text-gray-900 mb-2">
            Case not found
          </div>
          <div className="text-gray-500">
            The case you're looking for doesn't exist.
          </div>
        </div>
      </div>
    );
  }

  const handleProcessDocument = async (docId: number) => {
    try {
      await processDocument.mutateAsync(docId);
      showToast.success("Processing started", "Document is being analyzed by AI.");
    } catch (error) {
      console.error("Failed to process document:", error);
      showToast.error("Processing failed", "Could not start document processing.");
    }
  };

  const handleDeleteDocument = async (docId: number) => {
    if (!confirm("Are you sure you want to delete this document?")) return;

    try {
      await deleteDocument.mutateAsync(docId);
      showToast.success("Document deleted", "The document has been removed.");
    } catch (error) {
      console.error("Failed to delete document:", error);
      showToast.error("Delete failed", "Could not delete the document.");
    }
  };

  return (
    <div className="h-screen overflow-hidden flex flex-col">
      {/* Header */}
      <CaseDetailHeader case={caseItem} onStartChat={() => setShowChat(true)} />

      {/* Main Content */}
      <div className="relative flex flex-1 overflow-hidden">
        {/* Left/Main Section */}
        <div
          className={`flex-1 overflow-y-auto transition-all duration-300 ${
            showChat ? "lg:pr-[680px] xl:pr-[720px]" : ""
          }`}
        >
          <div className="max-w-7xl mx-auto p-6 space-y-6">
            {/* Case Overview */}
            <CaseOverview case={caseItem} />

            {/* Recent Documents */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle>Recent Documents</CardTitle>
                <Button variant="primary" size="sm" onClick={() => setIsUploadDialogOpen(true)}>
                  <Upload className="h-4 w-4" />
                  Upload Document
                </Button>
              </CardHeader>
              <CardContent>
                {docsLoading ? (
                  <div className="text-center py-8 text-gray-500">
                    Loading documents...
                  </div>
                ) : documents.length === 0 ? (
                  <div className="text-center py-8">
                    <FileText className="h-12 w-12 text-gray-300 mx-auto mb-3" />
                    <div className="text-gray-500">No documents yet</div>
                    <div className="text-sm text-gray-400">
                      Upload a document to get started
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {documents.slice(0, 5).map((doc) => {
                      const fileIcon = getFileIcon(doc.file_type);
                      return (
                        <div
                          key={doc.id}
                          className="flex items-center justify-between p-3 border border-gray-100 rounded-lg hover:bg-gray-50 transition-colors"
                        >
                          <div className="flex items-center gap-3 flex-1 min-w-0">
                            <span className="text-xl flex-shrink-0">
                              {fileIcon}
                            </span>
                            <div className="flex-1 min-w-0">
                              <div className="font-medium text-gray-900 truncate">
                                {doc.filename}
                              </div>
                              <div className="text-xs text-gray-500">
                                {doc.document_type} •{" "}
                                {formatDate(doc.created_at, "MMM d, yyyy")}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 ml-4">
                            {doc.processing_status === "pending" && (
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => handleProcessDocument(doc.id)}
                                disabled={processDocument.isPending}
                              >
                                {processDocument.isPending && processDocument.variables === doc.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Play className="h-4 w-4" />
                                )}
                                {processDocument.isPending && processDocument.variables === doc.id ? "Processing..." : "Process"}
                              </Button>
                            )}
                            <span
                              className={`text-xs px-2 py-1 rounded-md ${
                                doc.processing_status === "completed"
                                  ? "bg-green-100 text-green-800"
                                  : doc.processing_status === "processing"
                                    ? "bg-blue-100 text-blue-800"
                                    : "bg-gray-100 text-gray-600"
                              }`}
                            >
                              {doc.processing_status}
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="p-1 h-8 w-8"
                              onClick={() => handleDeleteDocument(doc.id)}
                              disabled={deleteDocument.isPending}
                            >
                              <Trash2 className="h-4 w-4 text-red-500" />
                            </Button>
                          </div>
                        </div>
                      );
                    })}
                    {documents.length > 5 && (
                      <Button variant="ghost" size="sm" className="w-full mt-2">
                        View all {documents.length} documents
                      </Button>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Hearings */}
            <HearingsList
              caseId={caseId}
              hearings={hearings}
              isLoading={hearingsLoading}
            />
          </div>
        </div>

        {/* Right Chat Panel */}
        {showChat && (
          <div className="absolute inset-y-0 right-0 z-20 w-full max-w-[720px]">
            <ChatPanel caseId={caseId} onClose={() => setShowChat(false)} />
          </div>
        )}
      </div>

      {/* Upload Document Dialog */}
      <UploadDocumentDialog
        isOpen={isUploadDialogOpen}
        onClose={() => setIsUploadDialogOpen(false)}
        defaultCaseId={caseId}
      />
    </div>
  );
}
