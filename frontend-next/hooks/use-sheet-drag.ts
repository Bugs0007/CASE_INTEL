"use client";

import { useCallback, useRef, type PointerEvent, type RefObject } from "react";

const CLOSE_DISTANCE = 110; // px dragged down that dismisses
const CLOSE_VELOCITY = 0.6; // px/ms flick that dismisses

/** Drag-down-to-dismiss for a bottom sheet: spread the handlers on the
 * grabber/header. The panel follows the finger (a transform), the backdrop
 * thins out, and on release the sheet either springs back or calls
 * `onClose` (which plays the normal exit). Only a downward drag counts, and
 * a mouse needs the primary button, and it does nothing at md and up. */
export function useSheetDrag(
  panelRef: RefObject<HTMLElement | null>,
  backdropRef: RefObject<HTMLElement | null>,
  onClose: () => void,
) {
  const drag = useRef<{ startY: number; lastY: number; lastT: number; velocity: number } | null>(null);

  const onPointerDown = useCallback(
    (event: PointerEvent) => {
      // Sheets only exist on a phone; on a desktop the header is just a header.
      if (typeof window.matchMedia !== "function" || !window.matchMedia("(max-width: 767px)").matches) return;
      if (event.pointerType === "mouse" && event.button !== 0) return;
      drag.current = { startY: event.clientY, lastY: event.clientY, lastT: performance.now(), velocity: 0 };
      (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
      if (panelRef.current) panelRef.current.style.transition = "none";
    },
    [panelRef],
  );

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      const d = drag.current;
      const panel = panelRef.current;
      if (!d || !panel) return;
      const dy = Math.max(0, event.clientY - d.startY);
      const now = performance.now();
      d.velocity = (event.clientY - d.lastY) / Math.max(1, now - d.lastT);
      d.lastY = event.clientY;
      d.lastT = now;
      panel.style.transform = `translateY(${dy}px)`;
      if (backdropRef.current) {
        backdropRef.current.style.opacity = String(Math.max(0.2, 1 - dy / (panel.offsetHeight || 400)));
      }
    },
    [panelRef, backdropRef],
  );

  const end = useCallback(
    (event: PointerEvent) => {
      const d = drag.current;
      const panel = panelRef.current;
      drag.current = null;
      if (!d || !panel) return;
      const dy = Math.max(0, event.clientY - d.startY);
      panel.style.transition = "transform 220ms cubic-bezier(0.2, 0.8, 0.2, 1)";
      if (backdropRef.current) backdropRef.current.style.opacity = "";
      if (dy > CLOSE_DISTANCE || d.velocity > CLOSE_VELOCITY) onClose();
      else panel.style.transform = "none";
    },
    [panelRef, backdropRef, onClose],
  );

  return { onPointerDown, onPointerMove, onPointerUp: end, onPointerCancel: end };
}
