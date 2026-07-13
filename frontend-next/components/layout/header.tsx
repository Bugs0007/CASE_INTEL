"use client";

import { useRouter } from "next/navigation";
import { SearchInput } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Calendar, LogOut, Upload } from "lucide-react";
import { clearToken } from "@/lib/auth";

export function Header() {
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6">
      {/* Global Search */}
      <div className="flex items-center gap-4 flex-1 max-w-md">
        <SearchInput
          placeholder="Search cases, documents, emails..."
          className="w-full"
        />
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-3">
        <Button variant="secondary" size="sm">
          <Calendar className="h-4 w-4" />
          Calendar
        </Button>

        <Button variant="primary" size="sm">
          <Upload className="h-4 w-4" />
          Quick Upload
        </Button>

        <Button variant="ghost" size="sm" onClick={handleLogout}>
          <LogOut className="h-4 w-4" />
          Log out
        </Button>
      </div>
    </header>
  );
}
