"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCase } from "@/hooks/use-cases";
import { useDocuments } from "@/hooks/use-documents";
import { useDeleteHearing, useHearings } from "@/hooks/use-hearings";
import { useCaseOrders, useViewOrder } from "@/hooks/use-court-orders";
import { useClientMessages } from "@/hooks/use-clients";
import { useViewportBudget } from "@/hooks/use-viewport-budget";
import { CaseOverview } from "@/components/cases/case-overview";
import { CaseDetailsDialog } from "@/components/cases/case-details-dialog";
import { DisposalBanner, UpdateRecipientsNote } from "@/components/cases/case-banners";
import { ClientContactsCard } from "@/components/cases/client-contacts-card";
import { CaseDetailSkeleton } from "@/components/cases/case-detail-skeleton";
import { CourtTrackingCard } from "@/components/cases/court-tracking-card";
import { CaseHeaderRow, FactsStrip } from "@/components/cases/compact/case-header";
import { PageDialog } from "@/components/cases/compact/compact-card";
import { CompactCalendar, CompactHearings, CompactOrderOverview } from "@/components/cases/compact/compact-main";
import {
  CompactClientUpdates,
  CompactDocuments,
  CompactFees,
  CompactNextHearing,
  CompactTasks,
} from "@/components/cases/compact/compact-rail";
import { HearingDialog } from "@/components/hearings/hearing-dialog";
import { ChatPanel } from "@/components/chat/chat-panel";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";
import { GenerateDocumentDialog } from "@/components/documents/generate-document-dialog";
import { DocumentViewer } from "@/components/documents/document-viewer";
import { CaseOrderCheckLine } from "@/components/cases/case-order-check-line";
import { OrderSyncStatusLine, hasOrderCheckLine } from "@/components/cases/order-sync-status";
import { useRefreshWhenOrdersArrive } from "@/hooks/use-order-sync";
import { showToast } from "@/components/ui/toaster";
import { useProcessDocument, useDeleteDocument } from "@/hooks/use-documents";
import { documentForOrder } from "@/lib/viewer-source";
import { latestOrderDocument, sortDocuments } from "@/lib/case-previews";
import { Users } from "lucide-react";
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
  const budget = useViewportBudget();
  const [showChat, setShowChat] = useState(false);
  const [isUploadDialogOpen, setIsUploadDialogOpen] = useState(false);
  const [isGenerateDialogOpen, setIsGenerateDialogOpen] = useState(false);
  const [isDetailsDialogOpen, setIsDetailsDialogOpen] = useState(false);
  const [isHearingDialogOpen, setIsHearingDialogOpen] = useState(false);
  const [editingHearing, setEditingHearing] = useState<Hearing | null>(null);
  const [trackingOpen, setTrackingOpen] = useState(false);
  const [detailsViewOpen, setDetailsViewOpen] = useState(false);
  // Whichever button opened a page dialog gets focus back when it closes.
  const dialogOpenerRef = useRef<HTMLElement | null>(null);
  // Opened by the Case Bot button: the viewer docks the bot at once.
  const [botDocked, setBotDocked] = useState(false);

  const { data: caseItem, isLoading: caseLoading, error: caseError } = useCase(caseId);
  // Orders saved by an order check show up without a reload.
  useRefreshWhenOrdersArrive(caseItem?.order_sync);

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

  const openDocument = (documentId: number, withBot = false) => {
    setShowChat(false);
    setBotDocked(withBot);
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

  // The Case Bot button reads the most recent order with the bot beside it;
  // a case with no documents has nothing to read, so the slide-over opens.
  const openBot = () => {
    const doc = latestOrderDocument(documents) ?? sortDocuments(documents)[0];
    if (doc) openDocument(doc.id, true);
    else setShowChat(true);
  };

  const openPageDialog = (open: () => void) => () => {
    dialogOpenerRef.current = document.activeElement as HTMLElement | null;
    open();
  };
  const openTracking = openPageDialog(() => setTrackingOpen(true));
  const openDetailsView = openPageDialog(() => setDetailsViewOpen(true));

  const viewingOrderId = viewOrder.isPending ? viewOrder.variables : undefined;

  return (
    <div className={cn("flex h-full flex-col", budget.fit ? "overflow-hidden" : "overflow-y-auto")}>
      <CaseHeaderRow
        caseItem={caseItem}
        onOpenTracking={openTracking}
        onOpenDetails={openDetailsView}
        onEditDetails={openEditDetails}
        onCaseBot={openBot}
      />
      <FactsStrip caseItem={caseItem} onSetSide={openEditDetails} onOpenDetails={openDetailsView} />

      {/* From 1024px wide and 700px tall this is one screen that never
          scrolls: each card shows exactly as many rows as the window has
          room for (useViewportBudget) and the rest is behind its expand
          button. Below that it is an ordinary single-column page. */}
      <div
        className={cn(
          "grid gap-[14px]",
          budget.fit ? "min-h-0 flex-1 px-5 py-[14px]" : "px-4 pb-24 pt-4 lg:pb-6",
        )}
        style={budget.fit ? { gridTemplateColumns: `minmax(0, 1fr) ${budget.railWidth}px` } : undefined}
      >
        <div className="flex min-h-0 min-w-0 flex-col gap-[14px]">
          <CompactOrderOverview
            caseItem={caseItem}
            orders={courtOrders}
            onViewOrder={handleViewOrder}
            viewingOrderId={viewingOrderId}
            onSetSide={openEditDetails}
          />
          <CompactHearings
            caseId={caseId}
            hearings={hearings}
            orders={courtOrders}
            rows={budget.hearingRows}
            isLoading={hearingsLoading}
            onAddHearing={handleAddHearing}
            onEditHearing={handleEditHearing}
            onDeleteHearing={handleDeleteHearing}
            deletingId={deleteHearing.variables}
            onViewOrder={handleViewOrder}
            viewingOrderId={viewingOrderId}
            statusLine={<CaseOrderCheckLine caseItem={caseItem} />}
          />
          <CompactCalendar
            caseId={caseId}
            hearings={hearings}
            caseItem={caseItem}
            mode={budget.calendar}
            items={budget.calendarItems}
            onEditDetails={openEditDetails}
          />
        </div>

        <aside aria-label="Case side panel" className="flex min-h-0 min-w-0 flex-col gap-[14px]">
          <CompactNextHearing hearings={hearings} />
          <CompactTasks
            caseId={caseId}
            caseTitle={caseItem.title}
            courtType={caseItem.court_type}
            latestOrder={latestDatedOrder}
            rows={budget.taskRows}
          />
          <CompactDocuments
            documents={documents}
            isLoading={docsLoading}
            rows={hasOrderCheckLine(caseItem) ? budget.documentRowsWithCheck : budget.documentRows}
            onUploadClick={() => setIsUploadDialogOpen(true)}
            onGenerateClick={() => setIsGenerateDialogOpen(true)}
            onView={(id) => openDocument(id)}
            onProcess={handleProcessDocument}
            onDelete={handleDeleteDocument}
            isProcessPending={processDocument.isPending}
            processingDocId={processDocument.variables}
            statusLine={<CaseOrderCheckLine caseItem={caseItem} />}
          />
          <CompactFees caseItem={caseItem} hearings={hearings} />
          {budget.showClientUpdates && <CompactClientUpdates caseItem={caseItem} onEditDetails={openEditDetails} />}
        </aside>
      </div>

      <PageDialog
        isOpen={trackingOpen}
        onClose={() => setTrackingOpen(false)}
        title="Court tracking"
        returnFocusRef={dialogOpenerRef}
      >
        <CourtTrackingCard caseItem={caseItem} hearings={hearings} />
      </PageDialog>

      <PageDialog
        isOpen={detailsViewOpen}
        onClose={() => setDetailsViewOpen(false)}
        title="Case details"
        icon={<Users className="h-4 w-4" />}
        returnFocusRef={dialogOpenerRef}
      >
        <div className="space-y-4">
          <DisposalBanner caseItem={caseItem} />
          <UpdateRecipientsNote caseItem={caseItem} onEditDetails={openEditDetails} />
          <CaseOverview case={caseItem} onEditDetails={openEditDetails} />
          <OrderSyncStatusLine caseItem={caseItem} />
          <ClientContactsCard contacts={caseItem.client_contacts} onEditDetails={openEditDetails} />
        </div>
      </PageDialog>

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
          chatInitiallyOpen={botDocked}
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
