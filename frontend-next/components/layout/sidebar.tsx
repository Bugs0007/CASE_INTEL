"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { hearingKeys } from "@/hooks/use-hearings";
import { hearingsApi } from "@/lib/api/hearings";
import { caseKeys } from "@/hooks/use-cases";
import { casesApi } from "@/lib/api/cases";
import { useRecentCases } from "@/hooks/use-recent-cases";
import { formatBadge, useReviewCount } from "@/hooks/use-review-count";
import { AccountMenu } from "@/components/layout/account-menu";
import { NAV_ITEMS, isNavActive } from "@/components/layout/nav-config";
import { NewMenu } from "@/components/layout/new-menu";

/** The desktop sidebar: brand, a New menu, five tabs, the last few cases
 * opened, and the account menu pinned at the bottom. 208px wide; below `lg`
 * it is hidden and MobileNav takes over. */
export function Sidebar() {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const recentCases = useRecentCases();
  const reviewCount = useReviewCount();

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
    <div className="ci-sidebar ci-on-field hidden lg:flex fixed left-0 top-0 h-screen w-52 flex-col z-10">
      {/* Brand -- Newsreader wordmark + mono eyebrow, 67px so its rule lines
          up with the top bar's. */}
      <div className="flex h-[67px] flex-shrink-0 items-center gap-2 border-b border-[var(--ci-field-line)] px-4">
        <Link href="/dashboard" className="font-serif text-[19px] text-[color:var(--ci-on-field)]">
          Case Intel
        </Link>
        <span className="mt-1 font-mono text-[9px] uppercase tracking-[0.14em] text-[color:var(--ci-on-field-dim)]">
          eCourts
        </span>
      </div>

      <div className="mx-3 mb-2.5 mt-3.5">
        <NewMenu variant="sidebar" />
      </div>

      {/* Navigation -- color/hover/active states come from .ci-sidebar a in
          case-intel-theme.css (dim by default, brightens on hover, a
          seal-red inset stripe for the current page via aria-current). */}
      <nav aria-label="Main" className="flex flex-shrink-0 flex-col gap-px px-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = isNavActive(pathname, item);
          const badge = item.href === "/messages" ? reviewCount : 0;
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              onMouseEnter={item.href === "/calendar" ? prefetchCalendar : undefined}
              className={cn(
                "flex h-10 items-center gap-3 rounded-md px-3 text-sm transition-colors hover:bg-[var(--ci-field-2)]",
                isActive ? "bg-[var(--ci-field-2)] font-semibold" : "font-medium",
              )}
            >
              <Icon className="h-[18px] w-[18px] flex-shrink-0" strokeWidth={1.8} />
              <span className="flex-1">{item.label}</span>
              {badge > 0 && (
                <span
                  data-testid="messages-badge"
                  aria-label={`${badge} awaiting review`}
                  className="flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--ci-seal)] px-1.5 text-[11px] font-bold tabular-nums text-white"
                >
                  {formatBadge(badge)}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Recent cases -- hidden until there is one. */}
      <div className="min-h-0 flex-1 overflow-hidden px-2">
        {recentCases.length > 0 && (
          <section
            aria-label="Recent cases"
            className="mt-3.5 border-t border-[var(--ci-field-line)] pt-4"
          >
            <h2 className="mb-1.5 px-3 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-[color:var(--ci-on-field-dim)]">
              Recent cases
            </h2>
            <ul>
              {recentCases.map((recent) => (
                <li key={recent.id}>
                  <Link
                    href={`/cases/${recent.id}`}
                    title={recent.title}
                    aria-current={pathname === `/cases/${recent.id}` ? "page" : undefined}
                    className="flex h-8 items-center gap-2.5 rounded px-3 text-[13px] font-medium hover:bg-[var(--ci-field-2)]"
                  >
                    <span
                      aria-hidden="true"
                      className="h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[color:var(--ci-on-field-dim)]"
                    />
                    <span className="truncate">{recent.title}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {/* Account -- pinned to the bottom; its menu opens upward. */}
      <div className="flex-shrink-0 border-t border-[var(--ci-field-line)] p-2">
        <AccountMenu variant="sidebar" />
      </div>
    </div>
  );
}
