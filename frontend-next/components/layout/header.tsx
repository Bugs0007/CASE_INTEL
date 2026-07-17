"use client";

import { useRouter } from "next/navigation";
import { Search, Calendar, LogOut, Upload } from "lucide-react";
import { clearToken } from "@/lib/auth";
import { useDialogs } from "@/providers/dialog-provider";

export function Header() {
  const router = useRouter();
  const { openUploadDocument } = useDialogs();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <header className="h-16 bg-white border-b border-gray-100 flex items-center justify-between px-7 sticky top-0 z-[5]">
      {/* Global Search */}
      <div className="flex items-center gap-2.5 flex-1 max-w-[360px] h-[38px] rounded-lg border border-gray-200 bg-gray-50 px-3">
        <Search className="h-4 w-4 text-gray-400 flex-shrink-0" strokeWidth={1.8} />
        <span className="text-sm text-gray-400 truncate">
          Search cases, documents, emails&hellip;
        </span>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2.5">
        <button
          onClick={() => router.push("/calendar")}
          className="inline-flex items-center gap-2 h-9 px-3.5 rounded-lg border border-gray-200 bg-white text-gray-800 text-[13px] font-semibold hover:bg-gray-50 transition-colors"
        >
          <Calendar className="h-[15px] w-[15px]" strokeWidth={1.8} />
          Calendar
        </button>

        <button
          onClick={openUploadDocument}
          className="inline-flex items-center gap-2 h-9 px-3.5 rounded-lg border-none bg-primary text-white text-[13px] font-semibold hover:bg-primary-hover transition-colors"
        >
          <Upload className="h-[15px] w-[15px]" strokeWidth={1.8} />
          Upload Document
        </button>

        <button
          onClick={handleLogout}
          className="inline-flex items-center gap-2 h-9 px-3 rounded-lg border-none bg-transparent text-gray-600 text-[13px] font-semibold hover:bg-gray-50 transition-colors"
        >
          <LogOut className="h-[15px] w-[15px]" strokeWidth={1.8} />
          Log Out
        </button>
      </div>
    </header>
  );
}
