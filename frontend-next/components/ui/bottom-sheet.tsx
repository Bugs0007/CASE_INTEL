"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { isTopModal, useModalLayer } from "@/hooks/use-modal-layer";
import { useSheetDrag } from "@/hooks/use-sheet-drag";
import { cn } from "@/lib/utils";

const EXIT_MS = 260;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  /** Accessible name. */
  label: string;
  /** Header content; the close button sits at its right. */
  title?: ReactNode;
  /** "auto" is as tall as its content (up to the screen); "full" fills it. */
  size?: "auto" | "full";
  /** Pinned under the scrolling body (a composer, a primary action). */
  footer?: ReactNode;
  /** Class for the scrolling body. */
  bodyClassName?: string;
  children: ReactNode;
}

/** A phone's sheet: rises from the bottom edge over a fading backdrop, can be
 * dragged down by its grabber/header to dismiss, and slides away on close.
 *
 * Only transform and opacity animate. Esc and a tap on the backdrop close
 * it, Tab stays inside, the page behind does not scroll, and the exit plays
 * before it unmounts. Under prefers-reduced-motion it simply fades. */
export function BottomSheet({
  open,
  onClose,
  label,
  title,
  size = "auto",
  footer,
  bodyClassName,
  children,
}: BottomSheetProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(open);
  const [closing, setClosing] = useState(false);

  // Mount on open; keep mounted through the exit animation.
  useEffect(() => {
    if (open) {
      setMounted(true);
      setClosing(false);
      return;
    }
    if (!mounted) return;
    setClosing(true);
    const timer = window.setTimeout(() => {
      setMounted(false);
      setClosing(false);
    }, prefersReducedMotion() ? 0 : EXIT_MS);
    return () => window.clearTimeout(timer);
    // `mounted` is read only to skip the first closed render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useModalLayer(panelRef, open && mounted);

  useEffect(() => {
    if (!open || !mounted) return;
    panelRef.current?.focus({ preventScroll: true });
    const onKeyDown = (event: KeyboardEvent) => {
      const panel = panelRef.current;
      if (!panel || event.key !== "Escape" || !isTopModal(panel)) return;
      event.preventDefault();
      onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, mounted, onClose]);

  const dragHandlers = useSheetDrag(panelRef, backdropRef, onClose);

  if (!mounted || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-[44] flex items-end justify-center md:items-center">
      <div
        ref={backdropRef}
        aria-hidden="true"
        data-testid="bottom-sheet-backdrop"
        onMouseDown={(event) => {
          event.preventDefault();
          if (panelRef.current && isTopModal(panelRef.current)) onClose();
        }}
        className={cn(
          "absolute inset-0 bg-[rgba(14,26,44,0.5)] transition-opacity duration-[260ms] motion-reduce:transition-none",
          closing ? "opacity-0" : "animate-backdrop-in opacity-100 motion-reduce:animate-none",
        )}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        data-layer="44"
        tabIndex={-1}
        style={closing ? { transform: "translateY(100%)", transition: `transform ${EXIT_MS}ms cubic-bezier(0.4, 0, 1, 1)` } : undefined}
        className={cn(
          "relative flex w-full flex-col overflow-hidden bg-surface outline-none will-change-transform",
          "rounded-t-[14px] shadow-[0_-18px_50px_rgba(8,16,32,0.35)] md:max-w-xl md:rounded-[10px]",
          size === "full" ? "h-[calc(100dvh-12px)] md:h-[min(720px,90dvh)]" : "max-h-[calc(100dvh-24px)] md:max-h-[85dvh]",
          !closing && "animate-sheet-up motion-reduce:animate-none",
        )}
      >
        {/* Grabber + header: dragging either one down dismisses. */}
        <div {...dragHandlers} className="flex-shrink-0 touch-none select-none">
          <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-[var(--ci-ink-14)]" aria-hidden="true" />
          <div className="flex min-h-[48px] items-center gap-2 px-4 pb-1 pt-1">
            <h2 className="min-w-0 flex-1 truncate font-serif text-[18px] font-bold text-gray-900">{title ?? label}</h2>
            <button
              type="button"
              onClick={onClose}
              onPointerDown={(event) => event.stopPropagation()}
              aria-label={`Close ${label}`}
              className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-gray-500 active:bg-gray-100"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>
        <div className={cn("min-h-0 flex-1 overflow-y-auto overscroll-contain border-t border-gray-100", bodyClassName)}>{children}</div>
        {footer && <div className="flex-shrink-0 border-t border-gray-100 pb-[env(safe-area-inset-bottom,0px)]">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
