"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ChevronLeft, Search } from "lucide-react";
import { CaseBotButton } from "@/components/assistant/case-bot-button";
import { AccountMenu } from "@/components/layout/account-menu";
import { HelpMenu } from "@/components/layout/help-menu";
import { NewMenu } from "@/components/layout/new-menu";
import { SUBBAR_SLOT_ID, useMobileHeaderState } from "@/components/layout/mobile-chrome";
import { useDialogs } from "@/providers/dialog-provider";

/** The top bar: the search trigger on the left and the Help menu on the
 * right, 67px tall to line up with the sidebar's brand row.
 *
 * Below `lg` the sidebar is hidden, so the New and account menus that live
 * there appear here instead -- nothing becomes unreachable on a phone. */
export function Header() {
  const { openSearch } = useDialogs();
  const [shortcut, setShortcut] = useState("⌘K");
  // A page (the case page) can put a back arrow and its title where the
  // brand sits on a phone.
  const pageHeader = useMobileHeaderState();

  // The hint should name the key this machine actually has.
  useEffect(() => {
    const platform = navigator.platform || navigator.userAgent;
    if (!/mac|iphone|ipad/i.test(platform)) setShortcut("Ctrl K");
  }, []);

  return (
    // Below md the bar is fixed to the top and slides up out of view while
    // the page scrolls down (MobileChrome sets html[data-chrome]); the
    // slot under it holds a page's sticky row. From md up the wrapper
    // vanishes (display: contents) and the bar is the sticky 67px one it
    // always was.
    <div className="ci-mobile-header max-md:fixed max-md:inset-x-0 max-md:top-0 max-md:z-20 max-md:will-change-transform md:contents">
      <header className="ci-appbar ci-on-field sticky top-0 z-[5] flex h-[var(--mobile-header-h)] items-center gap-3 px-4 max-md:gap-1 max-md:pt-[env(safe-area-inset-top,0px)] max-sm:pl-[max(0.5rem,env(safe-area-inset-left))] max-sm:pr-[max(0.5rem,env(safe-area-inset-right))] sm:px-7 md:h-[67px]">
        {pageHeader ? (
          <div className="flex min-w-0 flex-1 items-center gap-0.5 lg:hidden" data-testid="mobile-page-header">
            <Link
              href={pageHeader.backHref}
              aria-label={pageHeader.backLabel}
              className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-[color:var(--ci-on-field)] active:bg-[rgba(241,240,234,0.12)]"
            >
              <ChevronLeft className="h-6 w-6" strokeWidth={1.8} />
            </Link>
            {/* At the top of the page the bar says where Back goes; once the
                page has scrolled past its own title, the title slides in to
                take that place (two layers crossfading, transform + opacity). */}
            <span className="relative block h-6 min-w-0 flex-1">
              <span className="absolute inset-0 truncate text-[14px] font-semibold leading-6 text-[color:var(--ci-on-field-dim)] transition-[opacity,transform] duration-300 motion-reduce:transition-none [html[data-scrolled=true]_&]:-translate-y-1.5 [html[data-scrolled=true]_&]:opacity-0">
                {pageHeader.backText}
              </span>
              <span
                data-testid="mobile-page-title"
                className="absolute inset-0 translate-y-1.5 truncate font-serif text-[17px] font-semibold leading-6 text-[color:var(--ci-on-field)] opacity-0 transition-[opacity,transform] duration-300 motion-reduce:transition-none [html[data-scrolled=true]_&]:translate-y-0 [html[data-scrolled=true]_&]:opacity-100"
              >
                {pageHeader.title}
              </span>
            </span>
          </div>
        ) : (
          /* Brand -- the Sidebar (which normally shows this) is hidden below lg,
             so this keeps the wordmark on screen instead of losing it. */
          <Link
            href="/dashboard"
            className="shrink-0 font-serif max-md:pl-2 text-[17px] text-[color:var(--ci-on-field)] max-md:flex-1 lg:hidden"
          >
            Case Intel
          </Link>
        )}

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

        <div className="ml-auto flex items-center gap-1.5 max-md:ml-0 max-md:gap-0 sm:gap-2.5">
          <button
            type="button"
            onClick={openSearch}
            aria-label="Search"
            title="Search"
            className="ci-btn ci-btn--line h-11 w-11 justify-center !p-0 max-md:!border-transparent md:hidden"
          >
            <Search className="h-[20px] w-[20px]" strokeWidth={1.8} />
          </button>

          <div className="lg:hidden">
            <NewMenu variant="icon" />
          </div>

          <CaseBotButton />

          {/* Guided tour and keyboard shortcuts: nothing a touch screen needs. */}
          <div className="max-md:hidden">
            <HelpMenu />
          </div>

          <div className="lg:hidden">
            <AccountMenu variant="avatar" />
          </div>
        </div>
      </header>
      <div id={SUBBAR_SLOT_ID} className="md:hidden" />
    </div>
  );
}
