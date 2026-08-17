"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Briefcase,
  FileText,
  Plus,
  Calendar,
  Settings,
  type LucideIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { hearingKeys } from "@/hooks/use-hearings";
import { hearingsApi } from "@/lib/api/hearings";
import { caseKeys } from "@/hooks/use-cases";
import { casesApi } from "@/lib/api/cases";
import { getUsername } from "@/lib/auth";
import { useDialogs } from "@/providers/dialog-provider";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  badge?: number;
}

// "Emails" is deliberately not in this list -- see Phase F: hidden from
// nav only, the /emails route/page and all backend email code are
// untouched and fully functional, so re-adding this one line is all it
// takes to bring it back. The explicit NavItem[] annotation (rather than
// a bare array literal) is what keeps `badge` a valid, type-checked
// field below even while no current entry sets one.
const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/cases", label: "Cases", icon: Briefcase },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/calendar", label: "Calendar", icon: Calendar },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const { openNewCaseChooser } = useDialogs();
  const [username, setUsername] = useState<string | null>(null);

  // Read on mount only -- localStorage isn't available during SSR, and the
  // token/username are only ever set client-side at login anyway.
  useEffect(() => {
    setUsername(getUsername());
  }, []);

  // Warms the Calendar's data on hover, since it's the heaviest nav
  // destination -- by the time the click lands, the query cache is often
  // already populated so the page mounts with data instead of a spinner.
  function prefetchCalendar() {
    queryClient.prefetchQuery({
      queryKey: hearingKeys.list({}),
      queryFn: () => hearingsApi.list({}),
    });
    queryClient.prefetchQuery({
      queryKey: caseKeys.list({ status: "all", since: undefined }),
      queryFn: () => casesApi.list(undefined, undefined),
    });
  }

  return (
    <div className="ci-sidebar ci-on-field hidden lg:flex fixed left-0 top-0 h-screen w-60 flex-col z-10">
      {/* Logo -- Newsreader wordmark + mono eyebrow subtitle, same pairing
          as the landing page's header mark, so the app doesn't feel like a
          different product once an advocate logs in. */}
      <div className="px-5 py-[22px] border-b border-[var(--ci-field-line)] flex items-baseline gap-2">
        <Link href="/dashboard" className="font-serif text-[19px] text-[color:var(--ci-on-field)]">
          Case Intel
        </Link>
        <span className="font-mono text-[10px] tracking-[0.16em] uppercase text-[color:var(--ci-on-field-dim)]">
          eCourts
        </span>
      </div>

      {/* New Case Button -- opens the chooser between the three real entry
          points (manual entry, Track by CNR, advocate search) rather than
          jumping straight to one of them. Uses the ci-btn primitive
          directly (not the <Button> component) since .ci-on-field flips
          its solid variant to paper-on-ink for contrast against this dark
          sidebar -- <Button>'s bg-primary doesn't know about that context. */}
      <div className="p-4">
        <button
          onClick={openNewCaseChooser}
          className="ci-btn ci-btn--solid w-full justify-center"
        >
          <Plus className="h-4 w-4" />
          New Case
        </button>
      </div>

      {/* Navigation -- color/hover/active states come from .ci-sidebar a
          in case-intel-theme.css (dim by default, brightens on hover, a
          seal-red inset stripe for the current page via aria-current). */}
      <nav className="flex-1 px-3 py-1 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              onMouseEnter={item.href === "/calendar" ? prefetchCalendar : undefined}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded text-sm transition-colors",
                isActive ? "font-semibold bg-[var(--ci-field-line)]" : "font-medium hover:bg-[var(--ci-field-line)]",
              )}
            >
              <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <span className="min-w-[18px] h-[18px] px-1.5 rounded-full bg-[var(--ci-field-line)] text-[color:var(--ci-on-field)] text-[11px] font-mono font-bold flex items-center justify-center">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-[var(--ci-field-line)] text-meta text-[color:var(--ci-on-field-dim)] truncate">
        Signed in as{" "}
        <span className="text-[color:var(--ci-on-field)] font-semibold">{username || "Advocate"}</span>
      </div>
    </div>
  );
}
