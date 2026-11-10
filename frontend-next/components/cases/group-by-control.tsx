"use client";

import { cn } from "@/lib/utils";
import type { CaseGrouping } from "@/lib/case-grouping";

export const GROUPING_OPTIONS: { key: CaseGrouping; label: string }[] = [
  { key: "none", label: "None" },
  { key: "court", label: "Court" },
  { key: "client", label: "Client" },
];

/** "Group by: None | Court | Client" -- a segmented control for the desktop
 * filter bar, styled like the status tabs beside it. */
export function GroupByControl({
  value,
  onChange,
}: {
  value: CaseGrouping;
  onChange: (next: CaseGrouping) => void;
}) {
  return (
    <div className="flex items-center gap-2.5">
      <span aria-hidden="true" className="text-[13px] font-semibold text-gray-500">
        Group by
      </span>
      <div role="group" aria-label="Group cases by" className="flex gap-1 rounded-lg bg-gray-100 p-1">
        {GROUPING_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            aria-pressed={value === option.key}
            onClick={() => onChange(option.key)}
            className={cn(
              "flex h-8 flex-shrink-0 items-center rounded-md px-3.5 text-[13px] font-semibold transition-[background-color,color,box-shadow] duration-200 motion-reduce:transition-none",
              value === option.key
                ? "bg-white text-gray-800 shadow-[0_1px_2px_rgba(20,23,31,0.08)]"
                : "text-gray-500 hover:text-gray-700",
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
