"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";
import { NewCaseChooserDialog } from "@/components/cases/new-case-chooser-dialog";

interface DialogContextValue {
  openUploadDocument: () => void;
  openNewCaseChooser: () => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

/**
 * Owns the single shared dialog instances so that layout chrome (Sidebar,
 * Header) -- which lives outside the page component tree and can't reach
 * page-local useState -- can open the exact same dialogs page content
 * uses, instead of each needing its own copy. Mounted once in
 * (dashboard)/layout.tsx, above Sidebar/Header/page content.
 *
 * NewCaseChooserDialog: there are three real ways to add a case now
 * (manual entry, Track by CNR, advocate-search/import -- see
 * core/views/case.py, core/views/case_tracking.py's CaseCnrLookupView,
 * core/views/advocate_search.py) -- this dialog is just a chooser
 * between the three already-built flows' own routes, not a form itself.
 */
export function DialogProvider({ children }: { children: ReactNode }) {
  const [isUploadDocumentOpen, setIsUploadDocumentOpen] = useState(false);
  const [isNewCaseChooserOpen, setIsNewCaseChooserOpen] = useState(false);

  return (
    <DialogContext.Provider
      value={{
        openUploadDocument: () => setIsUploadDocumentOpen(true),
        openNewCaseChooser: () => setIsNewCaseChooserOpen(true),
      }}
    >
      {children}

      <UploadDocumentDialog
        isOpen={isUploadDocumentOpen}
        onClose={() => setIsUploadDocumentOpen(false)}
      />
      <NewCaseChooserDialog
        isOpen={isNewCaseChooserOpen}
        onClose={() => setIsNewCaseChooserOpen(false)}
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
