"use client";

import { LayoutDashboard, Briefcase, FileText, Mail, Calendar, Plus, Search, Upload, LogOut } from "lucide-react";
import { mockAdvocateName } from "../mock-data";

const NAV_ITEMS = [
  { label: "Dashboard", icon: LayoutDashboard, active: true },
  { label: "Cases", icon: Briefcase, active: false },
  { label: "Documents", icon: FileText, active: false },
  { label: "Calendar", icon: Calendar, active: false },
  { label: "Emails", icon: Mail, active: false, badge: 12 },
];

/** A visual replica of the real app's sidebar + header chrome, built from
 * inert <div>/<span> elements only (no <Link>, no onClick navigation, no
 * data hooks) so the tour can look exactly like the real app without any
 * risk of a click firing real navigation or a network request. */
export function TourChrome({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-page">
      {/* Fake sidebar */}
      <div className="ci-sidebar ci-on-field hidden lg:flex fixed left-0 top-0 h-screen w-60 flex-col z-10">
        <div className="px-5 py-[22px] border-b border-[var(--ci-field-line)] flex items-baseline gap-2">
          <span className="font-serif text-[19px] text-[color:var(--ci-on-field)]">Case Intel</span>
          <span className="font-mono text-[10px] tracking-[0.16em] uppercase text-[color:var(--ci-on-field-dim)]">
            eCourts
          </span>
        </div>
        <div className="p-4">
          <span className="ci-btn ci-btn--solid w-full justify-center cursor-default select-none">
            <Plus className="h-4 w-4" />
            New Case
          </span>
        </div>
        <nav className="flex-1 px-3 py-1 flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <span
                key={item.label}
                aria-current={item.active ? "page" : undefined}
                className={`flex items-center gap-3 px-3 py-2.5 rounded text-sm select-none cursor-default ${
                  item.active ? "font-semibold bg-[var(--ci-field-line)]" : "font-medium"
                }`}
              >
                <Icon className="h-[18px] w-[18px]" strokeWidth={1.8} />
                <span className="flex-1">{item.label}</span>
                {item.badge && (
                  <span className="min-w-[18px] h-[18px] px-1.5 rounded-full bg-[var(--ci-field-line)] text-[color:var(--ci-on-field)] text-[11px] font-mono font-bold flex items-center justify-center">
                    {item.badge}
                  </span>
                )}
              </span>
            );
          })}
        </nav>
        <div className="px-5 py-4 border-t border-[var(--ci-field-line)] text-meta text-[color:var(--ci-on-field-dim)] truncate">
          Signed in as{" "}
          <span className="text-[color:var(--ci-on-field)] font-semibold">{mockAdvocateName}</span>
        </div>
      </div>

      <div className="flex-1 flex flex-col lg:ml-60 min-w-0">
        {/* Fake header */}
        <header className="ci-appbar ci-on-field h-16 flex items-center justify-between px-4 sm:px-7 sticky top-0 z-[5] gap-3">
          <span className="font-serif text-[17px] text-[color:var(--ci-on-field)] shrink-0 lg:hidden">
            Case Intel
          </span>
          <div className="hidden md:flex items-center gap-2.5 flex-1 max-w-[360px] h-[38px] rounded border border-[var(--ci-field-line)] bg-[rgba(241,240,234,0.06)] px-3">
            <Search className="h-4 w-4 text-[color:var(--ci-on-field-dim)] flex-shrink-0" strokeWidth={1.8} />
            <span className="text-sm text-[color:var(--ci-on-field-dim)] truncate">
              Search cases, documents, emails&hellip;
            </span>
          </div>
          <div className="flex items-center gap-1.5 sm:gap-2.5">
            <span className="ci-btn ci-btn--line hidden lg:inline-flex h-9 px-3.5 text-[13px] cursor-default select-none">
              <Calendar className="h-[15px] w-[15px]" strokeWidth={1.8} />
              Calendar
            </span>
            <span className="ci-btn ci-btn--solid h-9 px-3.5 text-[13px] hidden sm:inline-flex cursor-default select-none">
              <Upload className="h-[15px] w-[15px]" strokeWidth={1.8} />
              Upload Document
            </span>
            <span className="inline-flex items-center justify-center h-9 px-3 rounded text-[color:var(--ci-on-field-dim)] cursor-default select-none">
              <LogOut className="h-[15px] w-[15px]" strokeWidth={1.8} />
            </span>
          </div>
        </header>

        <main className="flex-1 min-w-0 px-4 sm:px-7 pt-6 pb-40 max-w-[1240px] mx-auto w-full">
          {children}
        </main>
      </div>
    </div>
  );
}
