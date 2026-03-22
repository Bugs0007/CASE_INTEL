"use client";

import { SearchInput } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Bell, Calendar, Upload } from "lucide-react";

export function Header() {
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

        <div className="relative">
          <Button variant="ghost" size="sm" className="p-2">
            <Bell className="h-5 w-5" />
          </Button>
          <span className="absolute -top-1 -right-1 h-5 w-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
            3
          </span>
        </div>
      </div>
    </header>
  );
}
