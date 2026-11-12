import { Bot, Briefcase, Calendar, Inbox, LayoutDashboard, Receipt, type LucideIcon } from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Routes that light this tab: the route itself and everything under it.
   * Documents lives under Cases and Clients under Billing, so those routes
   * are listed here rather than having tabs of their own. */
  match: string[];
}

// "Emails" is deliberately not in this list -- hidden from nav only; the
// /emails route and all backend email code are untouched.
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, match: ["/dashboard"] },
  { href: "/cases", label: "Cases", icon: Briefcase, match: ["/cases", "/documents"] },
  { href: "/calendar", label: "Calendar", icon: Calendar, match: ["/calendar"] },
  { href: "/messages", label: "Messages", icon: Inbox, match: ["/messages"] },
  { href: "/assistant", label: "Case Bot", icon: Bot, match: ["/assistant"] },
  { href: "/billing", label: "Billing", icon: Receipt, match: ["/billing", "/clients"] },
];

export function isNavActive(pathname: string | null, item: NavItem): boolean {
  if (!pathname) return false;
  return item.match.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}
