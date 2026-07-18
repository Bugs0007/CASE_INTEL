"use client";

import { useLayoutEffect, useRef, useState } from "react";
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
  const tabRefs = useRef<Partial<Record<string, HTMLButtonElement>>>({});
  const [indicatorStyle, setIndicatorStyle] = useState<{ left: number; width: number } | null>(
    null,
  );

  // Slides the active-tab pill to the newly active button -- re-measured on
  // resize too, since the tabs' widths are text-driven, not fixed.
  useLayoutEffect(() => {
    function updateIndicator() {
      const activeEl = tabRefs.current[activeStatus];
      if (activeEl) {
        setIndicatorStyle({ left: activeEl.offsetLeft, width: activeEl.offsetWidth });
      }
    }
    updateIndicator();
    window.addEventListener("resize", updateIndicator);
    return () => window.removeEventListener("resize", updateIndicator);
  }, [activeStatus]);

  const handleSearchChange = (value: string) => {
    setSearchValue(value);
    onSearchChange(value);
  };

  return (
    <div className="flex items-center justify-between gap-4 flex-wrap">
      {/* Search */}
      <div className="flex items-center gap-2.5 w-full sm:w-80 h-11 sm:h-10 rounded-lg border border-gray-200 bg-white px-3">
        <Search className="h-4 w-4 text-gray-400 flex-shrink-0" strokeWidth={1.8} />
        <input
          type="text"
          value={searchValue}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="Search by case, client, or party"
          className="flex-1 min-w-0 bg-transparent text-sm text-gray-800 placeholder:text-gray-400 outline-none"
        />
      </div>

      {/* Status Tabs -- segmented control with a sliding active-tab pill.
          Scrolls horizontally, contained to this control, instead of
          overflowing the page when all 5 tabs don't fit a narrow screen. */}
      <div className="relative flex gap-1 bg-gray-100 rounded-lg p-1 min-w-0 max-w-full overflow-x-auto">
        {indicatorStyle && (
          <div
            aria-hidden="true"
            className="absolute top-1 bottom-1 rounded-md bg-white shadow-[0_1px_2px_rgba(20,23,31,0.08)] transition-all duration-300 ease-out motion-reduce:transition-none"
            style={{ left: indicatorStyle.left, width: indicatorStyle.width }}
          />
        )}
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.key}
            ref={(el) => {
              tabRefs.current[tab.key] = el ?? undefined;
            }}
            onClick={() => onStatusChange(tab.key)}
            className={cn(
              "relative z-10 h-11 sm:h-8 px-3.5 rounded-md text-[13px] font-semibold transition-colors flex-shrink-0 flex items-center",
              activeStatus === tab.key ? "text-gray-800" : "text-gray-500",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}
