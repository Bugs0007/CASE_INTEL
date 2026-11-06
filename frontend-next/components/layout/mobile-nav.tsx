"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Briefcase, FileText, Calendar, Inbox, Receipt, type LucideIcon } from "lucide-react";
import { formatBadge, useReviewCount } from "@/hooks/use-review-count";
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
  // Clients isn't here (six tabs is the most that keeps 44px+ targets at
  // 375px) -- it's one tap away from the Billing page header.
  { href: "/messages", label: "Inbox", icon: Inbox },
  { href: "/billing", label: "Billing", icon: Receipt },
];

/** A tab is lit on its own route and everything under it (a case page lights
 * Cases), so the bar always says where you are. */
function isActiveTab(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Bottom tab bar -- the mobile stand-in for the desktop Sidebar. Shown only
 * below `lg`; a shrunk copy of the 240px sidebar wouldn't give the 44px+ tap
 * targets this app's legal-staff users need, so this is a distinct pattern
 * rather than a responsive variant of the same component. Same dark ci-field
 * chrome as the Sidebar/Header, so the nav surface reads as one shell.
 *
 * The red marker over the active tab slides between tabs (a transform), the
 * active icon pops into its pill, a tab presses in under the thumb, and
 * Inbox carries the count of drafts waiting for review. */
export function MobileNav() {
  const pathname = usePathname();
  const reviewCount = useReviewCount();
  const items = NAV_ITEMS.map((item) => ({ ...item, badge: item.href === "/messages" ? reviewCount : item.badge }));
  const activeIndex = items.findIndex((item) => isActiveTab(pathname, item.href));

  return (
    <nav
      aria-label="Main"
      className="fixed bottom-0 left-0 right-0 z-30 border-t border-[var(--ci-field-line)] bg-[var(--ci-field)] pb-[env(safe-area-inset-bottom,0px)] pl-[env(safe-area-inset-left,0px)] pr-[env(safe-area-inset-right,0px)] lg:hidden"
    >
      <div className="relative grid h-16 items-stretch" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {activeIndex >= 0 && (
          <span
            aria-hidden="true"
            data-testid="nav-indicator"
            className="pointer-events-none absolute left-0 top-0 h-[2px] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] motion-reduce:transition-none"
            style={{ width: `${100 / items.length}%`, transform: `translateX(${activeIndex * 100}%)` }}
          >
            <span className="mx-auto block h-full w-8 rounded-b-sm bg-[var(--ci-seal)]" />
          </span>
        )}
        {items.map((item) => {
          const Icon = item.icon;
          const isActive = isActiveTab(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "relative flex min-w-0 flex-col items-center justify-center gap-0.5 pt-0.5 text-[11px] font-medium [--press-scale:0.9] transition-colors",
                isActive ? "font-semibold text-[color:var(--ci-on-field)]" : "text-[color:var(--ci-on-field-dim)]",
              )}
            >
              <span className="relative flex h-7 w-11 items-center justify-center">
                {/* The pill behind the active icon grows in and settles. */}
                <span
                  aria-hidden="true"
                  className={cn(
                    "absolute inset-0 rounded-full bg-[rgba(241,240,234,0.12)] transition-[transform,opacity] duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] motion-reduce:transition-none",
                    isActive ? "scale-100 opacity-100" : "scale-50 opacity-0",
                  )}
                />
                <Icon
                  key={isActive ? "on" : "off"}
                  className={cn("relative h-5 w-5", isActive && "animate-pop-in motion-reduce:animate-none")}
                  strokeWidth={isActive ? 2.2 : 1.8}
                />
                {item.badge ? (
                  <span
                    data-testid="nav-badge"
                    aria-label={`${item.badge} awaiting review`}
                    className="absolute right-0.5 top-0 flex h-[15px] min-w-[15px] animate-pop-in items-center justify-center rounded-full bg-[var(--ci-seal)] px-1 font-mono text-[9px] font-bold text-white motion-reduce:animate-none"
                  >
                    {formatBadge(item.badge)}
                  </span>
                ) : null}
              </span>
              <span className="max-w-full truncate">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
