"use client";

import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

/** The phone's top bar and the pieces pages hang on it.
 *
 *  - <MobileChromeController/> watches the page's scroller (the element
 *    marked `data-page-scroll`) and tells the CSS, through two attributes on
 *    <html>, whether the page has moved (`data-scrolled`) and whether the
 *    top bar should slide away (`data-chrome="hidden"`: reading down the
 *    page) or come back (scrolling up, or near the top). The bar itself
 *    only ever moves with a transform.
 *  - useMobileHeader() lets a page replace the brand with a back arrow and
 *    its own title in that bar.
 *  - <MobileSubbar/> puts a page's sticky row (tabs, filters) inside the bar,
 *    under the part that slides away, so it stays put at the top of the
 *    screen while the rest hides. */

// ---------------------------------------------------------------------------
// The page's own header text (back arrow + title)
// ---------------------------------------------------------------------------

export interface MobileHeaderState {
  title: string;
  backHref: string;
  backLabel: string;
  /** Shown beside the arrow until the page has scrolled, when `title` takes over. */
  backText: string;
}

let current: MobileHeaderState | null = null;
const listeners = new Set<() => void>();

function setMobileHeader(next: MobileHeaderState | null) {
  current = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** What the top bar should show instead of the brand, or null. */
export function useMobileHeaderState(): MobileHeaderState | null {
  return useSyncExternalStore(subscribe, () => current, () => null);
}

/** Show a back arrow and `title` in the phone's top bar while this page is
 * mounted. Pass null (title not known yet) to keep the brand. */
export function useMobileHeader(title: string | null, backHref: string, backLabel: string, backText: string) {
  useEffect(() => {
    if (!title) return;
    setMobileHeader({ title, backHref, backLabel, backText });
    return () => setMobileHeader(null);
  }, [title, backHref, backLabel, backText]);
}

// ---------------------------------------------------------------------------
// Scroll behaviour
// ---------------------------------------------------------------------------

const HIDE_AFTER = 96; // px scrolled before the bar may hide
const DELTA = 8; // px of travel that counts as a direction change

export function MobileChromeController() {
  const pathname = usePathname();

  useEffect(() => {
    const root = document.documentElement;
    let lastY = 0;
    let scrolled = false;
    let hidden = false;

    const apply = () => {
      root.dataset.scrolled = scrolled ? "true" : "false";
      root.dataset.chrome = hidden ? "hidden" : "shown";
    };

    const onScroll = (event: Event) => {
      const el = event.target;
      if (!(el instanceof HTMLElement) || el.dataset.pageScroll === undefined) return;
      const y = el.scrollTop;
      const delta = y - lastY;
      let nextHidden = hidden;
      if (y < 24) nextHidden = false;
      else if (delta > DELTA && y > HIDE_AFTER) nextHidden = true;
      else if (delta < -DELTA) nextHidden = false;
      if (Math.abs(delta) > DELTA || y < 24) lastY = y;
      const nextScrolled = y > 8;
      if (nextHidden !== hidden || nextScrolled !== scrolled) {
        hidden = nextHidden;
        scrolled = nextScrolled;
        apply();
      }
    };

    apply();
    // Scroll events do not bubble; capturing on the document hears every
    // scroller, and the data attribute picks the page's own.
    document.addEventListener("scroll", onScroll, { capture: true, passive: true });
    return () => {
      document.removeEventListener("scroll", onScroll, { capture: true });
      delete root.dataset.chrome;
      delete root.dataset.scrolled;
    };
  }, []);

  // A new page starts at the top with the bar showing.
  useEffect(() => {
    document.documentElement.dataset.chrome = "shown";
    document.documentElement.dataset.scrolled = "false";
  }, [pathname]);

  return null;
}

// ---------------------------------------------------------------------------
// A sticky row inside the top bar
// ---------------------------------------------------------------------------

export const SUBBAR_SLOT_ID = "mobile-subbar-slot";

/** A page's sticky row (tabs, filter chips), drawn inside the top bar's slot
 * and so pinned to the top of the screen even while the bar above it slides
 * away. `height` (px) is reserved in the page's own flow so the content
 * starts below it. Renders nothing on md and up. */
export function MobileSubbar({
  height,
  className,
  children,
}: {
  height: number;
  className?: string;
  children: ReactNode;
}) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useEffect(() => {
    setSlot(document.getElementById(SUBBAR_SLOT_ID));
  }, []);

  return (
    <>
      <div aria-hidden="true" style={{ height }} className="md:hidden" />
      {slot &&
        createPortal(
          <div
            style={{ height }}
            className={cn(
              "animate-settle border-b border-gray-200 bg-surface shadow-[0_6px_14px_-12px_rgba(20,32,44,0.45)] motion-reduce:animate-none",
              className,
            )}
          >
            {children}
          </div>,
          slot,
        )}
    </>
  );
}
