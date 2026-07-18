"use client";

import type { ReactNode } from "react";

// Next.js remounts template.tsx on every navigation (unlike layout.tsx,
// which persists across sibling routes), so this replays the fade-in
// automatically each time the route changes -- no per-page wiring needed.
export default function DashboardTemplate({ children }: { children: ReactNode }) {
  return <div className="h-full animate-fade-up motion-reduce:animate-none">{children}</div>;
}
