"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import dynamic from "next/dynamic";
import {
  ArrowLeft,
  Bot,
  Download,
  FileText,
  Loader2,
  PanelLeft,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { showToast } from "@/components/ui/toaster";
import { ChatPanel } from "@/components/chat/chat-panel";
import { isTopModal, useModalLayer } from "@/hooks/use-modal-layer";
import { useDocumentFile } from "@/hooks/use-document-file";
import { matchesQuery, sortDocuments } from "@/lib/case-previews";
import { viewerKind } from "@/lib/viewer-source";
import { cn, formatDate, formatFileSize, getFileIcon } from "@/lib/utils";
import type { Citation, CourtOrder, Document } from "@/types";

// pdf.js is large: it is fetched when a PDF is first opened here and is
// never part of the case page's own bundle.
const PdfViewer = dynamic(() => import("@/components/documents/pdf-viewer"), {
  ssr: false,
  loading: () => <Loading label="Opening PDF…" />,
});

function Loading({ label }: { label: string }) {
  return (
    <div className="flex flex-1 items-center justify-center gap-2 text-sm text-gray-500">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

interface DocumentViewerProps {
  caseId: number;
  documentId: number;
  documents: Document[];
  orders: CourtOrder[];
  /** Show a different document (replaces the history entry: Back still
   * closes the viewer in one step). */
  onSelectDocument: (documentId: number) => void;
  onClose: () => void;
}

/** A document, full screen: the case's documents on the left, the file in
 * the middle, Case Bot on the right -- scoped to this case, with its sources
 * opening here. Both side panels fold away.
 *
 * Portaled to <body> (the dashboard template's transform would otherwise
 * shrink a fixed overlay to the page area). Its layer sits over the
 * expanded card dialogs, so a document opened from inside one returns there
 * on close, and under the app's own z-50 dialogs. */
export function DocumentViewer({
  caseId,
  documentId,
  documents,
  orders,
  onSelectDocument,
  onClose,
}: DocumentViewerProps) {
  const doc = documents.find((d) => d.id === documentId);
  const file = useDocumentFile(doc, orders);
  const panelRef = useRef<HTMLDivElement>(null);
  const [listOpen, setListOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [listFilter, setListFilter] = useState("");

  useModalLayer(panelRef, true);

  // Both side panels start open where there is room for three columns.
  useEffect(() => {
    const roomy = window.matchMedia?.("(min-width: 1024px)").matches ?? false;
    setListOpen(roomy);
    setChatOpen(roomy);
  }, []);

  // Focus in on open, and back to whatever had it on close.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    panelRef.current?.focus({ preventScroll: true });
    return () => {
      if (opener && document.contains(opener)) opener.focus({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const panel = panelRef.current;
      if (!panel || event.key !== "Escape" || !isTopModal(panel)) return;
      // Esc belongs to a text field (clearing a search, say) while one has focus.
      const target = event.target as HTMLElement | null;
      if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
      event.preventDefault();
      onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const openCitation = (citation: Citation) => {
    if (citation.document_id === null) return;
    if (documents.some((d) => d.id === citation.document_id)) {
      // The API sends a document and a passage, not a page number, so this
      // opens the document at its first page.
      onSelectDocument(citation.document_id);
    } else {
      showToast.error("Document unavailable", "That source is no longer on this case.");
    }
  };

  if (typeof document === "undefined") return null;

  const name = doc ? doc.display_name || doc.filename : "Document";
  const kind = doc ? viewerKind(doc) : "other";
  const listed = sortDocuments(documents).filter((d) =>
    matchesQuery(listFilter, d.display_name, d.filename, d.document_type),
  );

  return createPortal(
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-label={`Document viewer: ${name}`}
      data-layer="48"
      tabIndex={-1}
      className="fixed inset-0 z-[48] flex flex-col bg-surface outline-none animate-fade-in motion-reduce:animate-none"
    >
      <header className="flex flex-shrink-0 items-center gap-2 border-b border-gray-200 bg-surface px-2 py-2 sm:px-3">
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close viewer">
          <ArrowLeft className="h-4 w-4" />
          <span className="hidden sm:inline">Back to case</span>
        </Button>
        <Button
          variant={listOpen ? "secondary" : "ghost"}
          size="sm"
          className="px-2"
          onClick={() => setListOpen((v) => !v)}
          aria-pressed={listOpen}
          aria-label="Documents list"
          title="Documents list"
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold text-gray-900" title={name}>
            {name}
          </h2>
          {doc && (
            <p className="truncate text-xs text-gray-500">
              <span className="font-mono">{doc.document_type ?? "document"}</span>
              {doc.file_size ? ` · ${formatFileSize(doc.file_size)}` : ""}
            </p>
          )}
        </div>
        {file.status === "ready" && doc && (
          <a
            href={file.url}
            download={doc.filename}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-gray-200 bg-surface px-3 text-sm font-semibold text-gray-800 hover:bg-gray-50 md:h-8"
          >
            <Download className="h-4 w-4" />
            <span className="hidden sm:inline">Download</span>
            <span className="sr-only sm:hidden">Download</span>
          </a>
        )}
        <Button
          variant={chatOpen ? "primary" : "secondary"}
          size="sm"
          onClick={() => setChatOpen((v) => !v)}
          aria-pressed={chatOpen}
        >
          <Bot className="h-4 w-4" />
          <span className="hidden sm:inline">Case Bot</span>
        </Button>
      </header>

      <div className="relative flex min-h-0 flex-1">
        {listOpen && (
          <aside
            aria-label="Case documents"
            className="z-10 flex w-64 flex-shrink-0 flex-col border-r border-gray-200 bg-surface max-lg:absolute max-lg:inset-y-0 max-lg:left-0 max-lg:w-72 max-lg:shadow-card"
          >
            <div className="flex-shrink-0 border-b border-gray-100 p-2">
              <Input
                type="search"
                aria-label="Filter documents"
                placeholder="Filter documents"
                value={listFilter}
                onChange={(e) => setListFilter(e.target.value)}
                className="h-8"
              />
            </div>
            <ul className="min-h-0 flex-1 overflow-y-auto p-1.5">
              {listed.map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => {
                      onSelectDocument(d.id);
                      if (window.matchMedia?.("(min-width: 1024px)").matches === false) {
                        setListOpen(false);
                      }
                    }}
                    aria-current={d.id === documentId ? "true" : undefined}
                    className={cn(
                      "flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left hover:bg-gray-50",
                      d.id === documentId && "bg-gray-100",
                    )}
                  >
                    <span className="flex-shrink-0 text-base">{getFileIcon(d.file_type)}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-gray-900">
                        {d.display_name || d.filename}
                      </span>
                      <span className="block truncate text-xs text-gray-500">
                        {d.document_type} · {formatDate(d.created_at, "d MMM yyyy")}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
              {listed.length === 0 && (
                <li className="px-2 py-3 text-sm text-gray-500">No documents match.</li>
              )}
            </ul>
          </aside>
        )}

        <main className="flex min-w-0 flex-1 flex-col bg-gray-50">
          {!doc ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center text-sm text-gray-600">
              This document is no longer on the case.
            </div>
          ) : file.status === "loading" ? (
            <Loading label="Loading file…" />
          ) : file.status === "error" ? (
            <div className="flex flex-1 items-center justify-center p-6 text-center">
              <div className="max-w-sm">
                <p className="text-sm font-medium text-gray-900">This file could not be loaded.</p>
                <p className="mt-1 text-sm text-gray-600">{file.message}</p>
              </div>
            </div>
          ) : kind === "pdf" ? (
            <PdfViewer blob={file.blob} />
          ) : kind === "image" ? (
            <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto p-4">
              {/* eslint-disable-next-line @next/next/no-img-element -- a blob: URL, not an optimisable asset */}
              <img src={file.url} alt={name} className="max-h-full max-w-full object-contain" />
            </div>
          ) : (
            <div className="flex flex-1 items-center justify-center p-6">
              <div className="w-full max-w-sm rounded-xl border border-gray-200 bg-surface p-6 text-center shadow-card">
                <FileText className="mx-auto mb-3 h-12 w-12 text-gray-300" />
                <p className="break-words text-sm font-semibold text-gray-900">{name}</p>
                <p className="mt-1 text-xs text-gray-500">
                  {doc.document_type}
                  {doc.file_size ? ` · ${formatFileSize(doc.file_size)}` : ""}
                </p>
                <p className="mt-3 text-sm text-gray-600">
                  This file type can&apos;t be previewed here.
                </p>
                <a
                  href={file.url}
                  download={doc.filename}
                  className="mt-4 inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-primary px-4 text-sm font-semibold text-page hover:bg-primary-hover md:h-10"
                >
                  <Download className="h-4 w-4" />
                  Download
                </a>
              </div>
            </div>
          )}
        </main>

        {chatOpen && (
          <aside
            aria-label="Case Bot"
            className="z-10 flex min-h-0 w-[420px] flex-shrink-0 flex-col max-lg:absolute max-lg:inset-0 max-lg:w-full"
          >
            <ChatPanel
              caseId={caseId}
              compact
              onClose={() => setChatOpen(false)}
              onOpenCitation={openCitation}
              className="h-full"
            />
          </aside>
        )}
      </div>
    </div>,
    document.body,
  );
}
