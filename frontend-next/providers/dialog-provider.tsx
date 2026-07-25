"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";

interface DialogContextValue {
  openUploadDocument: () => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

/**
 * Owns the single shared UploadDocumentDialog instance so that layout
 * chrome (Sidebar, Header) -- which lives outside the page component tree
 * and can't reach page-local useState -- can open the exact same dialog
 * page content uses, instead of each needing its own copy. Mounted once in
 * (dashboard)/layout.tsx, above Sidebar/Header/page content.
 *
 * There's no equivalent "create case" dialog here -- a Case is only ever
 * created via the advocate-search/import flow (/cases/search), never a
 * direct-entry form (see CaseListView).
 */
export function DialogProvider({ children }: { children: ReactNode }) {
  const [isUploadDocumentOpen, setIsUploadDocumentOpen] = useState(false);

  return (
    <DialogContext.Provider
      value={{
        openUploadDocument: () => setIsUploadDocumentOpen(true),
      }}
    >
      {children}

      <UploadDocumentDialog
        isOpen={isUploadDocumentOpen}
        onClose={() => setIsUploadDocumentOpen(false)}
      />
    </DialogContext.Provider>
  );
}

export function useDialogs(): DialogContextValue {
  const ctx = useContext(DialogContext);
  if (!ctx) {
    throw new Error("useDialogs() must be called within a DialogProvider");
  }
  return ctx;
}
