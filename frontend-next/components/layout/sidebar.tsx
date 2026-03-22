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
  LogOut,
} from 'lucide-react';
import { cn } from '@/lib/utils';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/cases', label: 'Cases', icon: Briefcase },
  { href: '/documents', label: 'Documents', icon: FileText },
  { href: '/emails', label: 'Emails', icon: Mail, badge: 12 },
];

export function Sidebar() {
  const pathname = usePathname();

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
          onClick={() => {
            // TODO: Open create case dialog
          }}
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
                'flex items-center gap-3 px-4 py-2 rounded-lg transition-colors',
                isActive
                  ? 'bg-primary text-white'
                  : 'text-gray-300 hover:bg-sidebar-hover'
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

      {/* Footer */}
      <div className="px-4 py-6 border-t border-sidebar-active space-y-4">
        {/* Storage Indicator */}
        <div className="space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">Storage</span>
            <span className="text-gray-400">45 GB / 100 GB</span>
          </div>
          <div className="h-2 bg-sidebar-hover rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-purple-500"
              style={{ width: '45%' }}
            />
          </div>
        </div>

        {/* User Profile */}
        <div className="flex items-center gap-3 px-2 py-3 bg-sidebar-hover rounded-lg">
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-blue-400 to-purple-500" />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium truncate">Advocate</div>
            <div className="text-xs text-gray-400 truncate">advocate@caseintel.com</div>
          </div>
        </div>

        {/* Logout Button */}
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start text-gray-300"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </Button>
      </div>
    </div>
  );
}
