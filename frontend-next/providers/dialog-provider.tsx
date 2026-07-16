"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { CreateCaseDialog } from "@/components/cases/create-case-dialog";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";

interface DialogContextValue {
  openCreateCase: () => void;
  openUploadDocument: () => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

/**
 * Owns the single shared CreateCaseDialog/UploadDocumentDialog instances so
 * that layout chrome (Sidebar, Header) -- which lives outside the page
 * component tree and can't reach page-local useState -- can open the exact
 * same dialogs page content uses, instead of each needing its own copy.
 * Mounted once in (dashboard)/layout.tsx, above Sidebar/Header/page content.
 */
export function DialogProvider({ children }: { children: ReactNode }) {
  const [isCreateCaseOpen, setIsCreateCaseOpen] = useState(false);
  const [isUploadDocumentOpen, setIsUploadDocumentOpen] = useState(false);

  return (
    <DialogContext.Provider
      value={{
        openCreateCase: () => setIsCreateCaseOpen(true),
        openUploadDocument: () => setIsUploadDocumentOpen(true),
      }}
    >
      {children}

      <CreateCaseDialog
        isOpen={isCreateCaseOpen}
        onClose={() => setIsCreateCaseOpen(false)}
      />
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
