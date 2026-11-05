import { useEffect, type RefObject } from "react";

/** Shared behaviour of the full-screen layers (the expanded card dialog and
 * the document viewer): who is on top, Tab kept inside, page scroll locked.
 *
 * The app's own dialogs (edit, upload, ...) are plain `z-50` overlays that
 * sit above both. These layers carry a `data-layer` number instead
 * (higher = above), so each can tell whether it is the one that should be
 * answering Esc and Tab right now. */

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** True when no other modal sits above `panel`: no unlayered dialog at all,
 * and no layer with a higher number. */
export function isTopModal(panel: HTMLElement): boolean {
  const layer = Number(panel.dataset.layer ?? 0);
  return !Array.from(document.querySelectorAll<HTMLElement>('[aria-modal="true"]')).some(
    (el) =>
      el !== panel && (el.dataset.layer === undefined || Number(el.dataset.layer) > layer),
  );
}

// Reference-counted, so a layer opened from inside another one can't unlock
// the page when it closes first.
let scrollLocks = 0;
let savedOverflow = "";
let savedPaddingRight = "";

export function lockScroll() {
  if (scrollLocks++ === 0) {
    const { body, documentElement } = document;
    savedOverflow = body.style.overflow;
    savedPaddingRight = body.style.paddingRight;
    // Hiding overflow also removes the page's scrollbar, if it has one,
    // which would widen everything behind the dialog by that much the moment
    // it opens. Keep the gutter.
    const gutter = documentElement.clientWidth > 0 ? window.innerWidth - documentElement.clientWidth : 0;
    body.style.overflow = "hidden";
    if (gutter > 0) body.style.paddingRight = `${gutter}px`;
  }
}

export function unlockScroll() {
  if (--scrollLocks === 0) {
    document.body.style.overflow = savedOverflow;
    document.body.style.paddingRight = savedPaddingRight;
  }
}

/** While `active`: lock page scroll, and keep Tab / Shift+Tab inside
 * `panelRef` (wrapping at the ends, and pulling focus back in if it has
 * strayed). Does nothing for a key press while another modal is on top. */
export function useModalLayer(panelRef: RefObject<HTMLElement | null>, active: boolean) {
  useEffect(() => {
    if (!active) return;
    lockScroll();
    return unlockScroll;
  }, [active]);

  useEffect(() => {
    if (!active) return;

    const onKeyDown = (event: KeyboardEvent) => {
      const panel = panelRef.current;
      if (!panel || event.key !== "Tab" || !isTopModal(panel)) return;

      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => !el.closest("[hidden], [aria-hidden='true']"),
      );
      if (focusable.length === 0) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const current = document.activeElement as HTMLElement | null;
      const inside = !!current && panel.contains(current);

      if (!inside || (current === panel && !event.shiftKey)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && (current === first || current === panel)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && current === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [active, panelRef]);
}
