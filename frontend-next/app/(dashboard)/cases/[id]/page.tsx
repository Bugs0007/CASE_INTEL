"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useCase } from "@/hooks/use-cases";
import { useDocuments } from "@/hooks/use-documents";
import { useDeleteHearing, useHearings } from "@/hooks/use-hearings";
import { CaseDetailHeader } from "@/components/cases/case-detail-header";
import { CaseOverview } from "@/components/cases/case-overview";
import { CaseDetailSkeleton } from "@/components/cases/case-detail-skeleton";
import { CourtTrackingCard } from "@/components/cases/court-tracking-card";
import { HearingsList } from "@/components/hearings/hearings-list";
import { HearingDialog } from "@/components/hearings/hearing-dialog";
import { ChatPanel } from "@/components/chat/chat-panel";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";
import { RecentDocumentsCard } from "@/components/documents/recent-documents-card";
import { showToast } from "@/components/ui/toaster";
import { useProcessDocument, useDeleteDocument } from "@/hooks/use-documents";
import type { Hearing } from "@/types";

export default function CaseDetailPage() {
  const params = useParams();
  const caseId = Number(params.id);
  const [showChat, setShowChat] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [isHearingDialogOpen, setIsHearingDialogOpen] = useState(false);
  const [editingHearing, setEditingHearing] = useState<Hearing | null>(null);

  const { data: caseItem, isLoading: caseLoading } = useCase(caseId);
  const { data: documents = [], isLoading: docsLoading } = useDocuments({
    case_id: caseId,
  });
  const { data: hearings = [], isLoading: hearingsLoading } = useHearings({
    case_id: caseId,
  });

  const processDocument = useProcessDocument();
  const deleteDocument = useDeleteDocument();
  const deleteHearing = useDeleteHearing();

  if (caseLoading) {
    return <CaseDetailSkeleton />;
  }

  if (!caseItem) {
    return (
      <div className="flex items-center justify-center h-full">
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

  const handleAddHearing = () => {
    setEditingHearing(null);
    setIsHearingDialogOpen(true);
  };

  const handleEditHearing = (hearing: Hearing) => {
    setEditingHearing(hearing);
    setIsHearingDialogOpen(true);
  };

  const handleDeleteHearing = async (hearingId: number) => {
    if (!confirm("Are you sure you want to delete this hearing?")) return;

    try {
      await deleteHearing.mutateAsync(hearingId);
      showToast.success("Hearing deleted", "The hearing has been removed.");
    } catch (error) {
      console.error("Failed to delete hearing:", error);
      showToast.error("Delete failed", "Could not delete the hearing.");
    }
  };

  return (
    <div className="h-full overflow-hidden flex flex-col">
      {/* Header */}
      <CaseDetailHeader case={caseItem} onToggleChat={() => setShowChat((v) => !v)} />

      {/* Main Content — a real flex row, not an overlay: the chat panel is a
          persistent sibling column with its own height from this flex
          container, so it never depends on position:fixed/sticky (and the
          containing-block bugs that come with those) to stay put while the
          left column scrolls. */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left/Main Section */}
        <div className="flex-1 overflow-y-auto min-w-0">
          <div className="max-w-[900px] mx-auto px-7 pt-6 pb-[60px] space-y-5">
            {/* Case Overview */}
            <CaseOverview case={caseItem} />

            {/* Court Tracking */}
            <CourtTrackingCard caseItem={caseItem} hearings={hearings} />

            {/* Case Documents */}
            <RecentDocumentsCard
              documents={documents}
              isLoading={docsLoading}
              onUploadClick={() => setIsUploadDialogOpen(true)}
              onProcess={handleProcessDocument}
              onDelete={handleDeleteDocument}
              isProcessPending={processDocument.isPending}
              processingDocId={processDocument.variables}
              isDeletePending={deleteDocument.isPending}
            />

            {/* Hearings */}
            <HearingsList
              caseId={caseId}
              hearings={hearings}
              isLoading={hearingsLoading}
              onAddHearing={handleAddHearing}
              onEditHearing={handleEditHearing}
              onDeleteHearing={handleDeleteHearing}
              deletingId={deleteHearing.variables}
            />
          </div>
        </div>

        {/* Right Chat Panel — a persistent flex sibling, never an overlay */}
        {showChat && (
          <div className="w-full max-w-[720px] flex-shrink-0 min-h-0 animate-slide-in-right motion-reduce:animate-none">
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

      {/* Add/Edit Hearing Dialog */}
      <HearingDialog
        isOpen={isHearingDialogOpen}
        onClose={() => setIsHearingDialogOpen(false)}
        caseId={caseId}
        hearing={editingHearing}
      />
    </div>
  );
}
