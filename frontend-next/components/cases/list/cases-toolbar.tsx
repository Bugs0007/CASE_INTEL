"use client";

import { LayoutGrid, List } from "lucide-react";
import { ATTENTION_FILTERS, SORT_OPTIONS, parseSort, type AttentionFilter, type CaseSort } from "@/components/cases/list/model";
import type { CasesView } from "@/components/cases/list/use-cases-view";
import { cn } from "@/lib/utils";

/** One compact strip above the list: the attention counts as filter chips
 * (click to filter, click again to clear), then the sort and the List | Cards
 * switch. */
export function CasesToolbar({
  counts,
  active,
  onToggleFilter,
  sort,
  onSortChange,
  view,
  onViewChange,
}: {
  counts: Record<AttentionFilter, number>;
  active: AttentionFilter | null;
  onToggleFilter: (key: AttentionFilter) => void;
  sort: CaseSort;
  onSortChange: (next: CaseSort) => void;
  view: CasesView;
  onViewChange: (next: CasesView) => void;
}) {
  const chips = ATTENTION_FILTERS.filter((f) => counts[f.key] > 0 || active === f.key);
  return (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2" data-testid="cases-toolbar">
      <div role="group" aria-label="Needs attention" className="flex min-w-0 flex-wrap items-center gap-2">
        {chips.map((f) => {
          const on = active === f.key;
          return (
            <button
              key={f.key}
              type="button"
              aria-pressed={on}
              onClick={() => onToggleFilter(f.key)}
              className={cn(
                "flex h-9 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors md:h-8",
                on
                  ? "border-gray-800 bg-gray-800 text-white"
                  : "border-gray-200 bg-surface text-gray-700 hover:bg-gray-50",
              )}
            >
              {f.label}
              <span className={cn("tabular-nums", on ? "text-white/80" : "text-gray-500")}>({counts[f.key]})</span>
            </button>
          );
        })}
      </div>
      <div className="flex min-w-0 max-w-full items-center gap-3">
        <label className="flex min-w-0 items-center gap-2 whitespace-nowrap text-[13px] text-gray-500">
          Sort by
          <select
            value={sort}
            onChange={(e) => onSortChange(parseSort(e.target.value))}
            className="h-9 min-w-0 rounded-lg border border-gray-200 bg-surface px-2 text-[13px] font-medium text-gray-800 md:h-8"
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.key} value={o.key}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <div role="group" aria-label="View" className="flex shrink-0 gap-1 rounded-lg bg-gray-100 p-1">
          {(
            [
              { key: "list", label: "List", Icon: List },
              { key: "cards", label: "Cards", Icon: LayoutGrid },
            ] as const
          ).map(({ key, label, Icon }) => (
            <button
              key={key}
              type="button"
              aria-pressed={view === key}
              onClick={() => onViewChange(key)}
              className={cn(
                "flex h-8 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-semibold transition-colors",
                view === key ? "bg-white text-gray-800 shadow-[0_1px_2px_rgba(20,23,31,0.08)]" : "text-gray-500 hover:text-gray-700",
              )}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
              {/* Icon only on a narrow phone; the name stays for screen readers. */}
              <span className="max-sm:sr-only">{label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
