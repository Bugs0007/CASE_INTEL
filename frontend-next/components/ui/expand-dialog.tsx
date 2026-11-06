"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { isTopModal, useModalLayer } from "@/hooks/use-modal-layer";
import { showSearch } from "@/lib/case-previews";

const DURATION_MS = 280;
const REDUCED_DURATION_MS = 160;
const EASE_OUT = "cubic-bezier(0.22, 1, 0.36, 1)";
// The "rise" look (case page): fade and lift from slightly below and smaller.
const RISE_MS = 260;
const RISE_BACKDROP_MS = 200;
const RISE_EASE = "cubic-bezier(0.2, 0.8, 0.2, 1)";
const RISE_FROM = "translateY(10px) scale(0.965)";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** The transform that makes the (final-size, centred) panel look like it is
 * still the card it grew from: same centre, same size. FLIP -- the panel is
 * laid out once at its real size and only transform/opacity animate. */
function originTransform(origin: DOMRect, panel: DOMRect): string {
  if (!panel.width || !panel.height || !origin.width || !origin.height) return "none";
  const dx = origin.left + origin.width / 2 - (panel.left + panel.width / 2);
  const dy = origin.top + origin.height / 2 - (panel.top + panel.height / 2);
  const sx = origin.width / panel.width;
  const sy = origin.height / panel.height;
  return `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`;
}

interface ExpandDialogProps {
  isOpen: boolean;
  onClose: () => void;
  /** Accessible name of the dialog. */
  label: string;
  /** Header title; the item count is shown beside it. */
  title: ReactNode;
  count?: number;
  /** The card's primary actions (Add task, Upload, ...). */
  actions?: ReactNode;
  /** A search box appears once `count` is over the threshold. */
  search?: { value: string; onChange: (value: string) => void };
  /** The card to grow from and shrink back into. */
  originRef?: RefObject<HTMLElement | null>;
  /** The expand button; focus goes back here on close. */
  returnFocusRef?: RefObject<HTMLElement | null>;
  /** The case page's look: opens by rising 10px and scaling up from .965
   * (260ms) instead of growing out of the card; a lighter, 6px-blurred
   * backdrop; a 10px radius. */
  rise?: boolean;
  /** A band under the header for filter chips and a search box. */
  toolbar?: ReactNode;
  /** A one-line hint under the body. */
  footer?: ReactNode;
  children: ReactNode;
}

/** One reusable expanded view: a centred dialog over a blurred, dimmed page.
 *
 * It grows out of the card it belongs to and shrinks back on close
 * (transform + opacity only, ~280ms; a plain fade under
 * prefers-reduced-motion). Esc and a click on the backdrop close it, focus
 * is trapped inside and returned to the expand button, and the page behind
 * does not scroll. On a phone it is a full-screen sheet.
 *
 * Portaled to <body>: the dashboard template wraps pages in a transformed
 * element, which would otherwise become the containing block of this fixed
 * overlay and shrink it to the page area.
 *
 * Its z-index sits under the app's own dialogs (z-50) so an edit form opened
 * from inside the list appears on top of it. */
export function ExpandDialog({
  isOpen,
  onClose,
  label,
  title,
  count,
  actions,
  search,
  originRef,
  returnFocusRef,
  rise = false,
  toolbar,
  footer,
  children,
}: ExpandDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  // Stays true while the exit animation plays, after `isOpen` is already false.
  const [mounted, setMounted] = useState(false);

  useLayoutEffect(() => {
    const panel = panelRef.current;
    const backdrop = backdropRef.current;

    if (isOpen) {
      wasOpen.current = true;
      setMounted(true);
      if (!panel || !backdrop) return;

      const reduced = prefersReducedMotion();
      const duration = reduced ? REDUCED_DURATION_MS : rise ? RISE_MS : DURATION_MS;
      const ease = rise ? RISE_EASE : EASE_OUT;
      const backdropMs = reduced ? REDUCED_DURATION_MS : rise ? RISE_BACKDROP_MS : duration;

      // Measure the panel at its real size and position first.
      panel.style.transition = "none";
      panel.style.transform = "none";
      panel.style.opacity = "1";
      const finalRect = panel.getBoundingClientRect();
      const origin = originRef?.current?.getBoundingClientRect();

      panel.style.transform = reduced
        ? "none"
        : rise
          ? RISE_FROM
          : origin
            ? originTransform(origin, finalRect)
            : "none";
      panel.style.opacity = "0";
      backdrop.style.transition = "none";
      backdrop.style.opacity = "0";
      void panel.offsetWidth; // commit the starting state before animating

      panel.style.transition = `transform ${duration}ms ${ease}, opacity ${duration}ms ease-out`;
      backdrop.style.transition = `opacity ${backdropMs}ms ease-out`;
      panel.style.transform = "none";
      panel.style.opacity = "1";
      backdrop.style.opacity = "1";

      panel.focus({ preventScroll: true });
      return;
    }

    if (!wasOpen.current) return;
    wasOpen.current = false;
    returnFocusRef?.current?.focus({ preventScroll: true });

    if (!panel || !backdrop) {
      setMounted(false);
      return;
    }
    const reduced = prefersReducedMotion();
    const duration = reduced ? REDUCED_DURATION_MS : rise ? RISE_MS : DURATION_MS;
    const origin = originRef?.current?.getBoundingClientRect();
    panel.style.transition = `transform ${duration}ms ${rise ? RISE_EASE : EASE_OUT}, opacity ${duration}ms ease-out`;
    backdrop.style.transition = `opacity ${reduced ? REDUCED_DURATION_MS : rise ? RISE_BACKDROP_MS : duration}ms ease-out`;
    panel.style.transform = reduced
      ? "none"
      : rise
        ? RISE_FROM
        : origin
          ? originTransform(origin, panel.getBoundingClientRect())
          : "none";
    panel.style.opacity = "0";
    backdrop.style.opacity = "0";

    const timer = window.setTimeout(() => setMounted(false), duration + 30);
    return () => window.clearTimeout(timer);
    // The refs are stable objects; only opening/closing should re-run this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Page scroll locked and Tab kept inside while open.
  useModalLayer(panelRef, isOpen);

  useEffect(() => {
    if (!isOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      const panel = panelRef.current;
      // A dialog opened from inside this one (z-50) is on top: leave Esc to it.
      if (!panel || event.key !== "Escape" || !isTopModal(panel)) return;
      event.preventDefault();
      onClose();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  if ((!isOpen && !mounted) || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-[45] flex items-center justify-center">
      <div
        ref={backdropRef}
        data-testid="expand-dialog-backdrop"
        aria-hidden="true"
        className={rise ? "absolute inset-0 backdrop-blur-[6px]" : "absolute inset-0 backdrop-blur-[8px]"}
        style={{
          background: rise ? "rgba(14, 26, 44, 0.34)" : "color-mix(in srgb, var(--ci-ink) 45%, transparent)",
        }}
        onMouseDown={(event) => {
          // Without this the browser's own mousedown handling blurs the
          // button focus was just returned to.
          event.preventDefault();
          if (panelRef.current && isTopModal(panelRef.current)) onClose();
        }}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={label}
        data-layer="45"
        tabIndex={-1}
        className={
          rise
            ? "relative flex flex-col overflow-hidden bg-surface outline-none will-change-transform max-sm:h-[100dvh] max-sm:w-full sm:w-[min(960px,calc(100%-80px))] sm:max-h-[calc(100%-72px)] sm:rounded-[10px] sm:shadow-[0_30px_80px_rgba(8,16,32,0.38)]"
            : "relative flex flex-col overflow-hidden bg-surface outline-none will-change-transform max-sm:h-[100dvh] max-sm:w-full sm:w-[min(960px,90vw)] sm:max-h-[85vh] sm:rounded-lg sm:border sm:border-gray-200 sm:shadow-card"
        }
      >
        <div className="flex flex-shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-gray-100 px-4 py-3 sm:px-5 sm:py-3.5">
          <h2
            className={
              rise
                ? "flex min-w-0 items-center gap-2.5 font-serif text-xl font-bold text-gray-900"
                : "flex min-w-0 items-center gap-2 text-base font-semibold text-gray-900"
            }
          >
            {title}
            {count !== undefined && <span className="ci-chip ci-chip--none">{count}</span>}
          </h2>
          {search && count !== undefined && showSearch(count) && (
            <Input
              type="search"
              aria-label={`Search ${label}`}
              placeholder="Search"
              value={search.value}
              onChange={(e) => search.onChange(e.target.value)}
              className="h-9 w-full sm:ml-2 sm:w-56"
            />
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {actions}
            <button
              type="button"
              onClick={onClose}
              aria-label={`Close ${label}`}
              className="flex h-11 w-11 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 hover:text-gray-900 md:h-8 md:w-8"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
        {toolbar && (
          <div className="flex-shrink-0 border-b border-gray-100 bg-[#fbfaf7] px-4 py-2.5 sm:px-5">{toolbar}</div>
        )}
        {/* @container: cards size their inner grids off the space they are
            given (`@md:`), and this body is its own container, not the page's. */}
        <div className="@container min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-5">
          {children}
        </div>
        {footer && (
          <div className="flex-shrink-0 border-t border-gray-100 px-4 py-2.5 text-xs text-gray-500 sm:px-5">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
