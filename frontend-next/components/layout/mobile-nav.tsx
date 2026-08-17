"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Briefcase, FileText, Calendar, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

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
  { href: "/dashboard", label: "Home", icon: LayoutDashboard },
  { href: "/cases", label: "Cases", icon: Briefcase },
  { href: "/documents", label: "Docs", icon: FileText },
  { href: "/calendar", label: "Calendar", icon: Calendar },
];

/** Bottom tab bar -- the mobile stand-in for the desktop Sidebar. Shown only
 * below `lg`; a shrunk copy of the 240px sidebar wouldn't give the 44px+ tap
 * targets this app's legal-staff users need, so this is a distinct pattern
 * rather than a responsive variant of the same component. Same dark ci-field
 * chrome as the Sidebar/Header, so the nav surface reads as one shell. */
export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-30 flex h-[var(--mobile-nav-height)] items-stretch border-t border-[var(--ci-field-line)] bg-[var(--ci-field)] pb-[env(safe-area-inset-bottom,0px)] lg:hidden"
    >
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors",
              isActive
                ? "text-[color:var(--ci-on-field)] font-semibold shadow-[inset_0_2px_0_var(--ci-seal)]"
                : "text-[color:var(--ci-on-field-dim)]",
            )}
          >
            <span className="relative">
              <Icon className="h-5 w-5" strokeWidth={isActive ? 2.2 : 1.8} />
              {item.badge ? (
                <span className="absolute -right-2 -top-1.5 min-w-[15px] h-[15px] px-1 rounded-full bg-[var(--ci-field-line)] text-[color:var(--ci-on-field)] text-[9px] font-mono font-bold flex items-center justify-center">
                  {item.badge}
                </span>
              ) : null}
            </span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
