"use client";

import { useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CaseStatus } from "@/types";

interface CaseFiltersProps {
  onStatusChange: (status: CaseStatus | "all") => void;
  onSearchChange: (search: string) => void;
  activeStatus: CaseStatus | "all";
}

const STATUS_TABS = [
  { key: "all" as const, label: "All Cases" },
  { key: "open" as const, label: "Active" },
  { key: "pending" as const, label: "Pending" },
  { key: "closed" as const, label: "Closed" },
  { key: "archived" as const, label: "Archived" },
];

export function CaseFilters({
  onStatusChange,
  onSearchChange,
  activeStatus,
}: CaseFiltersProps) {
  const [searchValue, setSearchValue] = useState("");

  const handleSearchChange = (value: string) => {
    setSearchValue(value);
    onSearchChange(value);
  };

  return (
    <div className="flex items-center justify-between gap-4 flex-wrap">
      {/* Search */}
      <div className="flex items-center gap-2.5 w-80 h-10 rounded-lg border border-gray-200 bg-white px-3">
        <Search className="h-4 w-4 text-gray-400 flex-shrink-0" strokeWidth={1.8} />
        <input
          type="text"
          value={searchValue}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search by case, client, or party"
          className="flex-1 min-w-0 bg-transparent text-sm text-gray-800 placeholder:text-gray-400 outline-none"
        />
      </div>

      {/* Status Tabs -- segmented control */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onStatusChange(tab.key)}
            className={cn(
              "h-8 px-3.5 rounded-md text-[13px] font-semibold transition-colors",
              activeStatus === tab.key
                ? "bg-white text-gray-800 shadow-[0_1px_2px_rgba(20,23,31,0.08)]"
                : "bg-transparent text-gray-500",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}
