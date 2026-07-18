"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Briefcase, FileText, Mail, Calendar } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: LayoutDashboard },
  { href: "/cases", label: "Cases", icon: Briefcase },
  { href: "/documents", label: "Docs", icon: FileText },
  { href: "/calendar", label: "Calendar", icon: Calendar },
  { href: "/emails", label: "Emails", icon: Mail, badge: 12 },
];

/** Bottom tab bar -- the mobile stand-in for the desktop Sidebar. Shown only
 * below `lg`; a shrunk copy of the 240px sidebar wouldn't give the 44px+ tap
 * targets this app's legal-staff users need, so this is a distinct pattern
 * rather than a responsive variant of the same component. */
export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-30 flex h-16 items-stretch border-t border-gray-100 bg-white lg:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-medium transition-colors",
              isActive ? "text-primary-hover font-semibold" : "text-gray-500",
            )}
          >
            <span className="relative">
              <Icon className="h-5 w-5" strokeWidth={isActive ? 2.2 : 1.8} />
              {item.badge ? (
                <span className="absolute -right-2 -top-1.5 min-w-[15px] h-[15px] px-1 rounded-full bg-gray-100 text-[#4b5468] text-[9px] font-bold flex items-center justify-center">
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
