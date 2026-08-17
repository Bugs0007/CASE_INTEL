"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { FileEdit, Gavel, Search, X, type LucideIcon } from "lucide-react";

interface NewCaseChooserDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ChooserOption {
  href: string;
  icon: LucideIcon;
  title: string;
  description: string;
}

const OPTIONS: ChooserOption[] = [
  {
    href: "/cases/new",
    icon: FileEdit,
    title: "Enter Manually",
    description: "Type in the case details yourself -- useful for a case that hasn't shown up in a search yet.",
  },
  {
    href: "/cases/new?mode=cnr",
    icon: Gavel,
    title: "Track by CNR",
    description: "Fetch case details from eCourts by CNR number and pre-fill the form -- faster than typing everything by hand.",
  },
  {
    href: "/cases/search",
    icon: Search,
    title: "Search by Advocate",
    description: "Search eCourts by advocate name or bar code and import matching cases in bulk.",
  },
];

/** The single "how do I add a case" entry point -- previously the
 * Sidebar/Header "New Case" buttons jumped straight to /cases/search,
 * hiding the other two equally-real ways to add a case (manual entry,
 * Track by CNR) that only existed if you already knew their URLs. This
 * doesn't rebuild any of the three flows, just fixes what happens when
 * you click "New Case". Mounted once in the DialogProvider (same pattern
 * as UploadDocumentDialog) so both Sidebar and Header -- which live
 * outside any single page's component tree -- can open it. */
export function NewCaseChooserDialog({ isOpen, onClose }: NewCaseChooserDialogProps) {
  const router = useRouter();

  useEffect(() => {
    if (typeof document === "undefined") return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  function handleChoose(href: string) {
    onClose();
    router.push(href);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        role="dialog"
        aria-modal="true"
        aria-labelledby="new-case-chooser-title"
      >
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 id="new-case-chooser-title" className="text-lg font-semibold text-gray-900">
            Add a Case
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-3">
          {OPTIONS.map((option) => {
            const Icon = option.icon;
            return (
              <button
                key={option.href}
                type="button"
                onClick={() => handleChoose(option.href)}
                className="w-full flex items-start gap-3.5 p-4 rounded-lg border border-gray-200 text-left hover:border-primary hover:bg-gray-50 transition-colors"
              >
                <div className="p-2 bg-gray-100 rounded-lg flex-shrink-0">
                  <Icon className="h-5 w-5 text-gray-700" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-gray-900">{option.title}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{option.description}</div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
