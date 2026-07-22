"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Search, Calendar, LogOut, Upload, Plus } from "lucide-react";
import { clearToken, clearUsername } from "@/lib/auth";
import { logout } from "@/lib/api/auth";
import { useDialogs } from "@/providers/dialog-provider";

export function Header() {
  const router = useRouter();
  const { openUploadDocument, openCreateCase } = useDialogs();

  async function handleLogout() {
    // Best-effort: invalidate the token server-side too, so it can't be
    // reused if it ever leaked (e.g. from browser history/logs). Clear
    // local state and redirect regardless of whether the request succeeds.
    try {
      await logout();
    } catch {
      // Network error or already-invalid token -- proceed to clear local
      // state anyway, since the whole point is to end this session.
    }
    clearToken();
    clearUsername();
    router.push("/login");
  }

  return (
    <header className="h-16 bg-white border-b border-gray-100 flex items-center justify-between px-4 sm:px-7 sticky top-0 z-[5] gap-3">
      {/* Brand -- Sidebar (which normally shows this) is hidden below lg, so
          this keeps the wordmark on screen instead of losing it entirely. */}
      <Link href="/" className="text-[17px] font-bold text-primary-active shrink-0 lg:hidden">
        Case Intel
      </Link>

      {/* Global Search -- desktop/tablet only; hidden on mobile since there's
          no room and this input is decorative (no search wired up yet). */}
      <div className="hidden md:flex items-center gap-2.5 flex-1 max-w-[360px] h-[38px] rounded-lg border border-gray-200 bg-gray-50 px-3">
        <Search className="h-4 w-4 text-gray-400 flex-shrink-0" strokeWidth={1.8} />
        <span className="text-sm text-gray-400 truncate">
          Search cases, documents, emails&hellip;
        </span>
      </div>

      {/* Action Buttons -- full set at lg+, condensed to icon-only on mobile
          (Calendar drops entirely there since it's already a bottom tab). */}
      <div className="flex items-center gap-1.5 sm:gap-2.5">
        <button
          onClick={() => router.push("/calendar")}
          className="hidden lg:inline-flex items-center gap-2 h-9 px-3.5 rounded-lg border border-gray-200 bg-white text-gray-800 text-[13px] font-semibold hover:bg-gray-50 transition-colors"
        >
          <Calendar className="h-[15px] w-[15px]" strokeWidth={1.8} />
          Calendar
        </button>

        <button
          onClick={openCreateCase}
          aria-label="New Case"
          title="New Case"
          className="inline-flex lg:hidden items-center justify-center h-11 w-11 rounded-lg border border-gray-200 bg-white text-gray-800 hover:bg-gray-50 transition-colors"
        >
          <Plus className="h-[18px] w-[18px]" strokeWidth={1.8} />
        </button>

        <button
          onClick={openUploadDocument}
          aria-label="Upload Document"
          title="Upload Document"
          className="inline-flex items-center justify-center gap-2 h-11 w-11 px-0 lg:h-9 lg:w-auto lg:px-3.5 rounded-lg border-none bg-primary text-white text-[13px] font-semibold hover:bg-primary-hover transition-colors"
        >
          <Upload className="h-[18px] w-[18px] lg:h-[15px] lg:w-[15px]" strokeWidth={1.8} />
          <span className="hidden lg:inline">Upload Document</span>
        </button>

        <button
          onClick={handleLogout}
          aria-label="Log Out"
          title="Log Out"
          className="inline-flex items-center justify-center gap-2 h-11 w-11 px-0 lg:h-9 lg:w-auto lg:px-3 rounded-lg border-none bg-transparent text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <LogOut className="h-[18px] w-[18px] lg:h-[15px] lg:w-[15px]" strokeWidth={1.8} />
          <span className="hidden lg:inline text-[13px] font-semibold">Log Out</span>
        </button>
      </div>
    </header>
  );
}
