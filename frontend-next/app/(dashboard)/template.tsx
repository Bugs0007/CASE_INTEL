"use client";

import type { ReactNode } from "react";

// Next.js remounts template.tsx on every navigation (unlike layout.tsx,
// which persists across sibling routes), so this replays the fade-in
// automatically each time the route changes -- no per-page wiring needed.
export default function DashboardTemplate({ children }: { children: ReactNode }) {
  // min-h-full (not h-full): a fixed h-full clips at exactly main's visible
  // height, so on pages taller than the viewport (e.g. Calendar's day-detail
  // panel with 2+ hearings) the real content silently overflows past this
  // wrapper's own box with default overflow:visible. That desyncs <main>'s
  // scrollHeight from where content actually ends, so its pb-16 bottom-nav
  // clearance (see layout.tsx) lands short -- the last item stays hidden
  // behind MobileNav even scrolled all the way down. min-h-full lets this
  // wrapper grow to fit its content instead of being clipped to it.
  return <div className="min-h-full animate-fade-up motion-reduce:animate-none">{children}</div>;
}
