"use client";

import { Check, ChevronDown, Layers, SlidersHorizontal } from "lucide-react";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { GROUPING_OPTIONS } from "@/components/cases/group-by-control";
import type { CaseGrouping } from "@/lib/case-grouping";
import { cn } from "@/lib/utils";

/** The phone's way to group the Cases list: an options button beside the
 * search field opens a sheet with the choices, and once a grouping is on, a
 * chip under the search names it (and reopens the sheet). */

/** A 48px square button that sits beside the search field. */
export function MobileViewOptionsButton({ onClick, active }: { onClick: () => void; active: boolean }) {
  return (
    <button
      type="button"
      aria-label="View options"
      aria-haspopup="dialog"
      onClick={onClick}
      className={cn(
        "relative flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-[3px] border bg-surface text-gray-700",
        active ? "border-[var(--ci-ink)]" : "border-gray-200",
      )}
    >
      <SlidersHorizontal className="h-[18px] w-[18px]" strokeWidth={1.8} aria-hidden="true" />
      {active && (
        <span aria-hidden="true" className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-[var(--ci-ink)]" />
      )}
    </button>
  );
}

/** "Grouped by court" -- shown while a grouping is on. */
export function MobileGroupChip({ grouping, onClick }: { grouping: Exclude<CaseGrouping, "none">; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-label={`Grouped by ${grouping}. Change grouping`}
      onClick={onClick}
      className="flex h-11 items-center [--press-scale:0.97]"
    >
      <span className="flex h-8 animate-pop-in items-center gap-1.5 rounded-full bg-[var(--ci-ink)] pl-3 pr-2.5 text-[13px] font-semibold text-[color:var(--ci-paper)] motion-reduce:animate-none">
        <Layers className="h-3.5 w-3.5" aria-hidden="true" />
        Grouped by {grouping}
        <ChevronDown className="h-3.5 w-3.5 opacity-70" aria-hidden="true" />
      </span>
    </button>
  );
}

const DESCRIPTIONS: Record<CaseGrouping, string> = {
  none: "One list, as before",
  court: "A section for each court",
  client: "A section for each client",
};

export function MobileViewOptionsSheet({
  open,
  onClose,
  grouping,
  onGroupingChange,
}: {
  open: boolean;
  onClose: () => void;
  grouping: CaseGrouping;
  onGroupingChange: (next: CaseGrouping) => void;
}) {
  return (
    <BottomSheet open={open} onClose={onClose} label="View options" title="View options">
      <div className="py-1">
        <div className="px-4 pb-1 pt-2 font-mono text-[10.5px] uppercase tracking-[0.12em] text-gray-500">Group by</div>
        <ul role="radiogroup" aria-label="Group cases by">
          {GROUPING_OPTIONS.map((option) => {
            const selected = grouping === option.key;
            return (
              <li key={option.key}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  onClick={() => {
                    onGroupingChange(option.key);
                    onClose();
                  }}
                  className="flex min-h-14 w-full items-center gap-3 px-4 text-left"
                >
                  <span className="min-w-0 flex-1">
                    <span className={cn("block text-[15px]", selected ? "font-bold text-gray-900" : "font-semibold text-gray-800")}>
                      {option.label}
                    </span>
                    <span className="block text-[12.5px] text-gray-500">{DESCRIPTIONS[option.key]}</span>
                  </span>
                  {selected && <Check className="h-5 w-5 flex-shrink-0 text-[color:var(--ci-ink)]" aria-hidden="true" />}
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </BottomSheet>
  );
}
