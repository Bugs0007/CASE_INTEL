"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCase } from "@/hooks/use-cases";
import { useDocuments } from "@/hooks/use-documents";
import { useDeleteHearing, useHearings } from "@/hooks/use-hearings";
import { useCaseOrders, useViewOrder } from "@/hooks/use-court-orders";
import { useClientMessages } from "@/hooks/use-clients";
import { useSidePanel } from "@/hooks/use-side-panel";
import { CaseDetailHeader } from "@/components/cases/case-detail-header";
import { CaseOverview } from "@/components/cases/case-overview";
import { CaseDetailsDialog } from "@/components/cases/case-details-dialog";
import { DisposalBanner, UpdateRecipientsNote } from "@/components/cases/case-banners";
import { CaseFeesCard } from "@/components/cases/case-fees-card";
import { ClientContactsCard } from "@/components/cases/client-contacts-card";
import { NextHearingCard } from "@/components/cases/next-hearing-card";
import { OrderOverviewCard } from "@/components/cases/order-overview";
import { CaseDetailSkeleton } from "@/components/cases/case-detail-skeleton";
import { CourtTrackingCard } from "@/components/cases/court-tracking-card";
import { HearingsList } from "@/components/hearings/hearings-list";
import { TasksCard } from "@/components/tasks/tasks-card";
import { CaseCalendarCard } from "@/components/calendar/case-calendar-card";
import { HearingDialog } from "@/components/hearings/hearing-dialog";
import { ChatPanel } from "@/components/chat/chat-panel";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";
import { GenerateDocumentDialog } from "@/components/documents/generate-document-dialog";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { CaseClientUpdatesCard } from "@/components/client-updates/case-client-updates-card";
import { RecentDocumentsCard } from "@/components/documents/recent-documents-card";
import { OrderSyncStatusLine } from "@/components/cases/order-sync-status";
import { showToast } from "@/components/ui/toaster";
import { useProcessDocument, useDeleteDocument } from "@/hooks/use-documents";
import { documentForOrder } from "@/lib/viewer-source";
import { cn } from "@/lib/utils";
import { APIError } from "@/lib/api/client";
import { getUsername } from "@/lib/auth";
import { caseDisplayTitle } from "@/lib/dashboard/adapt";
import { pushRecentCase, removeRecentCase } from "@/lib/recent-cases";
import type { Citation, Hearing } from "@/types";

export default function CaseDetailPage() {
  const params = useParams();
  const caseId = Number(params.id);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const sidePanel = useSidePanel();
  const [showChat, setShowChat] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [isGenerateDialogOpen, setIsGenerateDialogOpen] = useState(false);
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false);
  const [isHearingDialogOpen, setIsHearingDialogOpen] = useState(false);
  const [editingHearing, setEditingHearing] = useState<Hearing | null>(null);

  const { data: caseItem, isLoading: caseLoading, error: caseError } = useCase(caseId);

  // The sidebar's "Recent cases": remember this case once it has loaded, and
  // forget it if it no longer exists (a stale entry that led here).
  const recentTitle = caseItem ? caseDisplayTitle(caseItem.title, caseItem.case_number) : null;
  useEffect(() => {
    if (recentTitle) pushRecentCase(getUsername(), { id: caseId, title: recentTitle });
  }, [caseId, recentTitle]);
  const caseNotFound = caseError instanceof APIError && caseError.status === 404;
  useEffect(() => {
    if (caseNotFound) removeRecentCase(getUsername(), caseId);
  }, [caseId, caseNotFound]);
  const { data: documents = [], isLoading: docsLoading } = useDocuments({
    case_id: caseId,
  });
  const { data: hearings = [], isLoading: hearingsLoading } = useHearings({
    case_id: caseId,
  });
  // Fetched once for the whole case and bucketed by date inside
  // HearingsList, rather than one request per hearing card.
  const { data: courtOrders = [], isLoading: ordersLoading } = useCaseOrders(caseId);
  // Same query (and cache entry) CaseClientUpdatesCard reads -- only its
  // loading state is needed here, see the skeleton gate below.
  const { isLoading: draftsLoading } = useClientMessages({ case_id: caseId, status: "draft" });

  // Most recent dated order: the default start for a limitation deadline.
  const latestDatedOrder = courtOrders.reduce<{ id: number; order_date: string } | null>(
    (latest, order) =>
      order.order_date && (!latest || order.order_date > latest.order_date)
        ? { id: order.id, order_date: order.order_date }
        : latest,
    null,
  );

  const processDocument = useProcessDocument();
  const deleteDocument = useDeleteDocument();
  const deleteHearing = useDeleteHearing();
  const viewOrder = useViewOrder();

  // The viewer lives in the URL (?doc=<id>) so a document can be linked and
  // the browser's Back button closes it. Opening pushes an entry; switching
  // documents inside the viewer replaces it, so one Back always returns to
  // the page.
  const viewerDocId = Number(searchParams.get("doc")) || null;
  const openedByPush = useRef(false);

  const openDocument = (documentId: number) => {
    setShowChat(false);
    openedByPush.current = true;
    router.push(`${pathname}?doc=${documentId}`, { scroll: false });
  };

  const switchDocument = (documentId: number) => {
    router.replace(`${pathname}?doc=${documentId}`, { scroll: false });
  };

  const closeViewer = () => {
    if (openedByPush.current) {
      openedByPush.current = false;
      router.back();
    } else {
      router.replace(pathname, { scroll: false });
    }
  };

  // Order Overview and the client-update drafts sit at the TOP of the page
  // and only render once their own queries answer. Showing the page before
  // then made them pop in above everything, shoving Edit Details and
  // Generate down between mouse-down and click -- the "first click does
  // nothing" report. All three queries start together, so waiting for the
  // two small ones costs almost nothing and the page appears once, in place.
  if (caseLoading || ordersLoading || draftsLoading) {
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
            The case you&apos;re looking for doesn&apos;t exist.
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

  // An order opens in the viewer through the document that holds its PDF.
  // When that document can't be told apart from the case's others (or isn't
  // listed), fall back to the PDF in a new tab, as before.
  const handleViewOrder = (orderId: number) => {
    const order = courtOrders.find((o) => o.id === orderId);
    const orderDocument = order ? documentForOrder(order, documents) : null;
    if (orderDocument) {
      openDocument(orderDocument.id);
      return;
    }
    viewOrder.mutate(orderId, {
      onError: (error) => {
        console.error("Failed to open order:", error);
        showToast.error("Could not open order", "Try again in a moment.");
      },
    });
  };

  // A Case Bot source opens its document in the viewer. The citation carries
  // a document and a passage but no page number, so it opens at page 1.
  const handleOpenCitation = (citation: Citation) => {
    if (citation.document_id === null) return;
    if (documents.some((d) => d.id === citation.document_id)) {
      openDocument(citation.document_id);
    } else {
      showToast.error("Document unavailable", "That source is no longer on this case.");
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

  const openEditDetails = () => setIsDetailsDialogOpen(true);

  return (
    <div className="h-full overflow-hidden flex flex-col">
      {/* Header */}
      <CaseDetailHeader
        case={caseItem}
        onToggleChat={() => setShowChat((v) => !v)}
        sidePanelOpen={sidePanel.open}
        onToggleSidePanel={sidePanel.toggle}
        onEditDetails={openEditDetails}
      />

      {/* Below 1100px this is one scrolling page (main column, then the
          rail). From 1100px it is two columns that scroll on their own, so
          the rail starts under the header and stays put while the main
          column scrolls. Each column is a @container: cards size their
          inner grids off the width they are actually given. */}
      <div className="flex-1 min-h-0 overflow-y-auto pb-[var(--mobile-nav-height)] lg:pb-10 min-[1100px]:flex min-[1100px]:overflow-hidden min-[1100px]:pb-0">
        <div className="@container min-w-0 min-[1100px]:flex-1 min-[1100px]:overflow-y-auto min-[1100px]:pb-[60px]">
          <div className="px-4 sm:px-7 pt-6 pb-6 min-[1100px]:pb-0 space-y-5">
            {/* The case looks disposed of: offer to close it (never
                automatic). */}
            <DisposalBanner caseItem={caseItem} />

            {/* Order Overview -- the AI summary of the most recent order,
                the "what just happened" the advocate opened the page for. */}
            <OrderOverviewCard
              orders={courtOrders}
              currentNextHearing={caseItem.next_hearing_date}
              onViewOrder={handleViewOrder}
              viewingOrderId={viewOrder.isPending ? viewOrder.variables : undefined}
            />

            {/* Client emails drafted from the latest order / hearing date,
                waiting for review. Renders nothing when there are none. */}
            <CaseClientUpdatesCard caseId={caseId} />
            <UpdateRecipientsNote caseItem={caseItem} onEditDetails={openEditDetails} />

            {/* Hearings & Orders */}
            <HearingsList
              caseId={caseId}
              hearings={hearings}
              isLoading={hearingsLoading}
              onAddHearing={handleAddHearing}
              onEditHearing={handleEditHearing}
              onDeleteHearing={handleDeleteHearing}
              deletingId={deleteHearing.variables}
              orders={courtOrders}
              onViewOrder={handleViewOrder}
              viewingOrderId={viewOrder.isPending ? viewOrder.variables : undefined}
            />

            {/* Calendar -- this case's hearings, deadlines (including the
                ones read from orders) and the advocate's own events. */}
            <CaseCalendarCard
              caseId={caseId}
              hearings={hearings}
              partyRole={caseItem.user_party_role}
              onEditDetails={openEditDetails}
            />

            {/* Court Tracking */}
            <CourtTrackingCard caseItem={caseItem} hearings={hearings} />
          </div>
        </div>

        {sidePanel.open && (
          <aside
            aria-label="Case side panel"
            className={cn(
              "@container min-w-0 px-4 sm:px-7 pb-6 space-y-5",
              "min-[1100px]:w-[400px] min-[1100px]:flex-shrink-0 min-[1100px]:overflow-y-auto",
              "min-[1100px]:border-l min-[1100px]:border-gray-100 min-[1100px]:px-5 min-[1100px]:pt-6",
            )}
          >
            <NextHearingCard hearings={hearings} />

            <TasksCard
              caseId={caseId}
              courtType={caseItem.court_type}
              latestOrder={latestDatedOrder}
            />

            <CaseOverview case={caseItem} onEditDetails={openEditDetails} />

            {/* Order check status -- so an empty documents list is never
                a silent zero: "none on the portal" vs "check failed". */}
            <OrderSyncStatusLine caseItem={caseItem} />

            <RecentDocumentsCard
              documents={documents}
              isLoading={docsLoading}
              onUploadClick={() => setIsUploadDialogOpen(true)}
              onGenerateClick={() => setIsGenerateDialogOpen(true)}
              onProcess={handleProcessDocument}
              onDelete={handleDeleteDocument}
              onView={openDocument}
              isProcessPending={processDocument.isPending}
              processingDocId={processDocument.variables}
              isDeletePending={deleteDocument.isPending}
            />

            <CaseFeesCard caseId={caseId} summary={caseItem.fee_summary} hearings={hearings} />

            <ClientContactsCard contacts={caseItem.client_contacts} onEditDetails={openEditDetails} />
          </aside>
        )}
      </div>

      {/* Case Bot -- a slide-over from the right at every width. Portaled to
          document.body: (dashboard)/template.tsx's page-transition wrapper
          uses `transform`, which per spec makes it the containing block for
          fixed descendants and would shrink "fixed inset-y-0" to that
          wrapper's box (leaving the Header and bottom MobileNav poking out
          around it). */}
      {showChat &&
        typeof document !== "undefined" &&
        createPortal(
          <div className="fixed inset-y-0 right-0 z-40 w-full sm:w-[min(680px,100vw)] bg-white shadow-2xl animate-slide-in-right motion-reduce:animate-none">
            <ChatPanel
              caseId={caseId}
              onClose={() => setShowChat(false)}
              onOpenCitation={handleOpenCitation}
              className="h-full"
            />
          </div>,
          document.body,
        )}

      {viewerDocId !== null && !docsLoading && (
        <DocumentViewer
          caseId={caseId}
          documentId={viewerDocId}
          documents={documents}
          orders={courtOrders}
          onSelectDocument={switchDocument}
          onClose={closeViewer}
        />
      )}

      {/* Upload Document Dialog */}
      <UploadDocumentDialog
        isOpen={isUploadDialogOpen}
        onClose={() => setIsUploadDialogOpen(false)}
        defaultCaseId={caseId}
      />

      <CaseDetailsDialog
        isOpen={isDetailsDialogOpen}
        onClose={() => setIsDetailsDialogOpen(false)}
        case={caseItem}
      />

      {/* Template-merge documents (vakalatnama, memo of appearance, ...) */}
      <GenerateDocumentDialog
        isOpen={isGenerateDialogOpen}
        onClose={() => setIsGenerateDialogOpen(false)}
        caseItem={caseItem}
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
