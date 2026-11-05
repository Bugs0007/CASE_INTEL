"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

export interface SectionTab {
  href: string;
  label: string;
}

/** Documents and Clients no longer have sidebar tabs: they sit beside the
 * page they belong to. Their routes are unchanged. */
export const CASES_TABS: SectionTab[] = [
  { href: "/cases", label: "Cases" },
  { href: "/documents", label: "Documents" },
];

export const BILLING_TABS: SectionTab[] = [
  { href: "/billing", label: "Billing" },
  { href: "/clients", label: "Clients" },
];

/** A strip of links between sibling pages, shown at the top of each. */
export function SectionTabs({ tabs, className }: { tabs: SectionTab[]; className?: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Section" className={cn("mb-5 flex gap-1 border-b border-gray-200", className)}>
      {tabs.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px flex h-11 items-center border-b-2 px-4 text-sm font-semibold transition-colors md:h-10",
              active
                ? "border-[var(--ci-ink)] text-gray-900"
                : "border-transparent text-gray-500 hover:text-gray-900",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
