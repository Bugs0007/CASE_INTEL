"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import {
  LayoutDashboard,
  Briefcase,
  FileText,
  Mail,
  Plus,
  Calendar,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useDialogs } from "@/providers/dialog-provider";
import { hearingKeys } from "@/hooks/use-hearings";
import { hearingsApi } from "@/lib/api/hearings";
import { caseKeys } from "@/hooks/use-cases";
import { casesApi } from "@/lib/api/cases";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/cases", label: "Cases", icon: Briefcase },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/calendar", label: "Calendar", icon: Calendar },
  { href: "/emails", label: "Emails", icon: Mail, badge: 12 },
];

export function Sidebar() {
  const pathname = usePathname();
  const { openCreateCase } = useDialogs();
  const queryClient = useQueryClient();

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
    <div className="fixed left-0 top-0 h-screen w-60 bg-white border-r border-gray-100 flex flex-col z-10">
      {/* Logo */}
      <div className="px-5 py-[22px] border-b border-gray-100">
        <Link href="/" className="text-[19px] font-bold text-primary-active">
          Case Intel
        </Link>
      </div>

      {/* New Case Button */}
      <div className="p-4">
        <button
          onClick={openCreateCase}
          className="w-full flex items-center justify-center gap-2 h-10 rounded-lg border-none bg-primary text-white text-sm font-semibold hover:bg-primary-hover transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Case
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-1 flex flex-col gap-0.5">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              onMouseEnter={item.href === "/calendar" ? prefetchCalendar : undefined}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                isActive
                  ? "bg-[#eef1fb] text-primary-hover font-semibold"
                  : "text-gray-600 font-medium hover:bg-gray-50",
              )}
            >
              <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
              <span className="flex-1">{item.label}</span>
              {item.badge && (
                <span className="min-w-[18px] h-[18px] px-1.5 rounded-full bg-gray-100 text-[#4b5468] text-[11px] font-bold flex items-center justify-center">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-gray-100 text-meta text-gray-500">
        Signed in as <span className="text-gray-800 font-semibold">Advocate</span>
      </div>
    </div>
  );
}
