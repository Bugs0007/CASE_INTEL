"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { MoreVertical, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** The kebab on a case card or row. The backdrop is portaled to <body>: a card
 * carries a CSS transform, which would make `position: fixed` relative to the
 * card instead of the screen. z-40 sits above the app's fixed chrome, so a
 * click anywhere outside the menu closes it and never reaches the row. */
export function CaseOptionsMenu({
  onDelete,
  isDeleting,
  className,
}: {
  onDelete?: () => void;
  isDeleting?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className={cn("relative flex-shrink-0", className)}>
      <Button
        variant="ghost"
        size="sm"
        className="p-1 h-11 w-11 md:h-8 md:w-8"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        aria-haspopup="true"
        aria-expanded={open}
        aria-label="Case options"
      >
        <MoreVertical className="h-4 w-4" />
      </Button>
      {open && (
        <>
          {typeof document !== "undefined" &&
            createPortal(
              <div
                className="fixed inset-0 z-40"
                onClick={(e) => {
                  e.stopPropagation();
                  setOpen(false);
                }}
              />,
              document.body,
            )}
          <div
            role="menu"
            onClick={(e) => e.stopPropagation()}
            className="absolute right-0 top-full mt-1 w-40 bg-surface rounded-lg shadow-lg border border-gray-100 py-1 z-50"
          >
            <button
              role="menuitem"
              disabled={isDeleting}
              onClick={() => {
                setOpen(false);
                onDelete?.();
              }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-status-alert-soft disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Trash2 className="h-4 w-4" />
              {isDeleting ? "Deleting..." : "Delete Case"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
