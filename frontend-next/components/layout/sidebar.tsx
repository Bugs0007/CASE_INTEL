'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/button';
import {
  LayoutDashboard,
  Briefcase,
  FileText,
  Mail,
  Plus,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useDialogs } from '@/providers/dialog-provider';

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/cases", label: "Cases", icon: Briefcase },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/emails", label: "Emails", icon: Mail, badge: 12 },
];

export function Sidebar() {
  const pathname = usePathname();
  const { openCreateCase } = useDialogs();

  return (
    <div className="fixed left-0 top-0 h-screen w-64 bg-sidebar text-white flex flex-col border-r border-sidebar-active">
      {/* Logo */}
      <div className="px-6 py-6 border-b border-sidebar-active">
        <Link href="/" className="text-2xl font-bold text-white">
          ⚖️ Case Intel
        </Link>
      </div>

      {/* New Case Button */}
      <div className="px-4 py-4">
        <Button
          variant="primary"
          size="md"
          className="w-full"
          onClick={openCreateCase}
        >
          <Plus className="h-4 w-4" />
          New Case
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-2">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-4 py-2 rounded-lg transition-colors",
                isActive
                  ? "bg-primary text-white"
                  : "text-gray-300 hover:bg-sidebar-hover",
              )}
            >
              <Icon className="h-5 w-5" />
              <span className="text-sm font-medium flex-1">{item.label}</span>
              {item.badge && (
                <span className="bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
                  {item.badge}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
