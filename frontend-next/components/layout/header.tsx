"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { AccountMenu } from "@/components/layout/account-menu";
import { HelpMenu } from "@/components/layout/help-menu";
import { NewMenu } from "@/components/layout/new-menu";
import { useDialogs } from "@/providers/dialog-provider";

/** The top bar: the search trigger on the left and the Help menu on the
 * right, 67px tall to line up with the sidebar's brand row.
 *
 * Below `lg` the sidebar is hidden, so the New and account menus that live
 * there appear here instead -- nothing becomes unreachable on a phone. */
export function Header() {
  const { openSearch } = useDialogs();
  const [shortcut, setShortcut] = useState("⌘K");

  // The hint should name the key this machine actually has.
  useEffect(() => {
    const platform = navigator.platform || navigator.userAgent;
    if (!/mac|iphone|ipad/i.test(platform)) setShortcut("Ctrl K");
  }, []);

  return (
    <header className="ci-appbar ci-on-field sticky top-0 z-[5] flex h-[67px] items-center gap-3 px-4 sm:px-7">
      {/* Brand -- the Sidebar (which normally shows this) is hidden below lg,
          so this keeps the wordmark on screen instead of losing it. */}
      <Link href="/dashboard" className="shrink-0 font-serif text-[17px] text-[color:var(--ci-on-field)] lg:hidden">
        Case Intel
      </Link>

      <button
        type="button"
        onClick={openSearch}
        aria-label="Search cases, documents, clients"
        className="hidden h-[38px] max-w-[360px] flex-1 items-center gap-2.5 rounded border border-[var(--ci-field-line)] bg-[rgba(241,240,234,0.06)] px-3 text-left hover:border-[color:var(--ci-on-field-dim)] md:flex"
      >
        <Search className="h-4 w-4 flex-shrink-0 text-[color:var(--ci-on-field-dim)]" strokeWidth={1.8} />
        <span className="flex-1 truncate text-sm text-[color:var(--ci-on-field-dim)]">
          Search cases, documents, clients
        </span>
        <kbd className="rounded-sm border border-[var(--ci-field-line)] bg-[var(--ci-field)] px-1.5 py-0.5 font-mono text-[11px] text-[color:var(--ci-on-field-dim)]">
          {shortcut}
        </kbd>
      </button>

      <div className="ml-auto flex items-center gap-1.5 sm:gap-2.5">
        <button
          type="button"
          onClick={openSearch}
          aria-label="Search"
          title="Search"
          className="ci-btn ci-btn--line h-11 w-11 justify-center !p-0 md:hidden"
        >
          <Search className="h-[18px] w-[18px]" strokeWidth={1.8} />
        </button>

        <div className="lg:hidden">
          <NewMenu variant="icon" />
        </div>

        <HelpMenu />

        <div className="lg:hidden">
          <AccountMenu variant="avatar" />
        </div>
      </div>
    </header>
  );
}
