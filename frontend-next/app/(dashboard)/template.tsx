"use client";

import type { ReactNode } from "react";

// Next.js remounts template.tsx on every navigation (unlike layout.tsx,
// which persists across sibling routes), so this replays the fade-in
// automatically each time the route changes -- no per-page wiring needed.
export default function DashboardTemplate({ children }: { children: ReactNode }) {
  // flex-1 min-h-0 overflow-y-auto (the same recipe Case Detail's own inner
  // column already uses) makes THIS div the scrolling element, not <main>.
  // That split matters: flex-basis:0% (flex-1) + min-height:0 together give
  // this div a genuinely definite resolved height regardless of its
  // content -- required for Case Detail's own h-full root to correctly
  // fill "the rest of main" and do its own internal scrolling (a page
  // taller than the viewport otherwise falls back to being sized by its
  // *content* here, cascading "auto" all the way down through every nested
  // percentage-height descendant, which is what broke Case Detail's "only
  // the middle column scrolls" layout into "the whole page scrolls"
  // instead of the chat sliding in over an internally-scrolled page).
  // Because this div both clips (min-h-0) AND scrolls (overflow-y-auto)
  // its own content, pages taller than the viewport (Calendar's
  // day-detail list) still get a real scrollbar and correct bottom-nav
  // clearance -- just from this element instead of from <main>.
  return (
    // data-page-scroll: MobileChrome reads this scroller to hide the phone's
    // top bar while reading down. Below md the bar is fixed over the page, so
    // the scroller starts under it (padding-top) and the page slides in from
    // the right on every navigation; md and up keep the plain fade-up.
    <div
      data-page-scroll
      className="flex-1 min-h-0 min-w-0 overflow-y-auto overscroll-y-contain pb-[var(--mobile-nav-height)] max-md:pt-[var(--mobile-header-h)] lg:pb-0 animate-fade-up max-md:animate-page-in motion-reduce:animate-none"
    >
      {children}
    </div>
  );
}
