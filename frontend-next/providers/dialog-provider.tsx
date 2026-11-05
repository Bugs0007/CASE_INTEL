"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { UploadDocumentDialog } from "@/components/documents/upload-document-dialog";
import { NewCaseChooserDialog } from "@/components/cases/new-case-chooser-dialog";
import { SearchDialog } from "@/components/layout/search-dialog";
import { ShortcutsDialog } from "@/components/layout/shortcuts-dialog";
import { isTypingTarget, shortcutFor } from "@/lib/shortcuts";

interface DialogContextValue {
  openUploadDocument: () => void;
  openNewCaseChooser: () => void;
  openSearch: () => void;
  openShortcuts: () => void;
}

const DialogContext = createContext<DialogContextValue | null>(null);

/**
 * Owns the single shared dialog instances so that layout chrome (Sidebar,
 * Header) -- which lives outside the page component tree and can't reach
 * page-local useState -- can open the exact same dialogs page content
 * uses, instead of each needing its own copy. Mounted once in
 * (dashboard)/layout.tsx, above Sidebar/Header/page content.
 *
 * It also owns the app-wide keyboard shortcuts (N, U, ?, Ctrl/Cmd+K), since
 * those just open these same dialogs; see lib/shortcuts.ts for when they
 * are ignored.
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
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);

  const openUploadDocument = useCallback(() => setIsUploadDocumentOpen(true), []);
  const openNewCaseChooser = useCallback(() => setIsNewCaseChooserOpen(true), []);
  const openSearch = useCallback(() => setIsSearchOpen(true), []);
  const openShortcuts = useCallback(() => setIsShortcutsOpen(true), []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const action = shortcutFor(event, {
        typing: isTypingTarget(event.target),
        modalOpen: document.querySelector('[aria-modal="true"]') !== null,
      });
      if (!action) return;
      event.preventDefault();
      if (action === "search") setIsSearchOpen(true);
      else if (action === "new-case") setIsNewCaseChooserOpen(true);
      else if (action === "upload") setIsUploadDocumentOpen(true);
      else setIsShortcutsOpen(true);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <DialogContext.Provider value={{ openUploadDocument, openNewCaseChooser, openSearch, openShortcuts }}>
      {children}

      <UploadDocumentDialog
        isOpen={isUploadDocumentOpen}
        onClose={() => setIsUploadDocumentOpen(false)}
      />
      <NewCaseChooserDialog
        isOpen={isNewCaseChooserOpen}
        onClose={() => setIsNewCaseChooserOpen(false)}
      />
      <SearchDialog isOpen={isSearchOpen} onClose={() => setIsSearchOpen(false)} />
      <ShortcutsDialog isOpen={isShortcutsOpen} onClose={() => setIsShortcutsOpen(false)} />
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
