"use client";

import { useState } from "react";
import { SearchInput } from "@/components/ui/input";
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
    <div className="space-y-4">
      {/* Search */}
      <SearchInput
        placeholder="Search cases..."
        value={searchValue}
        onChange={(e) => handleSearchChange(e.target.value)}
        className="max-w-md"
      />

      {/* Status Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-gray-200">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => onStatusChange(tab.key)}
            className={cn(
              "px-4 py-2 text-sm font-medium border-b-2 transition-colors",
              activeStatus === tab.key
                ? "border-blue-500 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}
