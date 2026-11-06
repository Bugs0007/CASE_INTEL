"use client";

import { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { useModalLayer } from "@/hooks/use-modal-layer";
import { SHORTCUT_LIST } from "@/lib/shortcuts";

/** The keyboard shortcuts, from the Help menu or by pressing "?". */
export function ShortcutsDialog({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null);
  useModalLayer(panelRef, isOpen);

  useEffect(() => {
    if (!isOpen) return;
    panelRef.current?.focus({ preventScroll: true });
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onMouseDown={onClose} aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        tabIndex={-1}
        className="relative w-full max-w-sm rounded-lg border border-gray-200 bg-surface p-5 shadow-card outline-none"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">Keyboard shortcuts</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close keyboard shortcuts"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-900"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <ul className="divide-y divide-gray-100">
          {SHORTCUT_LIST.map((shortcut) => (
            <li key={shortcut.label} className="flex items-center justify-between py-2.5 text-sm">
              <span className="text-gray-800">{shortcut.label}</span>
              <span className="flex items-center gap-1.5">
                {shortcut.keys.map((key, i) => (
                  <span key={key} className="flex items-center gap-1.5">
                    {i > 0 && <span className="text-xs text-gray-400">or</span>}
                    <kbd className="rounded-sm border border-gray-200 bg-page px-1.5 py-0.5 font-mono text-xs text-gray-700">
                      {key}
                    </kbd>
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs text-gray-500">Letter shortcuts are off while you are typing in a field.</p>
      </div>
    </div>
  );
}
