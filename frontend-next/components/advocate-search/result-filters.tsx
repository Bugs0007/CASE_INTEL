"use client";

import { useEffect, useRef, useState } from "react";
import { Eye, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ResultFilters } from "@/lib/advocate-search-results";
import { courtOptions, statusCounts, yearBounds } from "@/lib/advocate-search-results";
import type { AdvocateResultRow, MatchStatus } from "@/types";

const field =
  "h-8 rounded-md border border-gray-300 bg-surface px-2.5 text-[13px] outline-none focus:ring-2 focus:ring-primary";
const chipCls = (on: boolean) =>
  cn(
    "h-[30px] whitespace-nowrap rounded-full border px-3 text-[12.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
    on ? "border-primary bg-primary text-page" : "border-gray-200 bg-surface text-gray-600 hover:bg-gray-100",
  );

/** The filter bar over the results: a search across case number, parties,
 * advocate and court; status chips; court and year range; match chips; and a
 * "Show hidden" popover with the two groups that start hidden. All of it lives in
 * the URL (see the page), and none of it asks the portal anything. */
export function ResultFiltersBar({
  filters,
  onChange,
  rows,
  counts,
}: {
  filters: ResultFilters;
  onChange: (next: ResultFilters) => void;
  rows: AdvocateResultRow[];
  counts: Partial<Record<MatchStatus, number>>;
}) {
  const [popover, setPopover] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const set = (patch: Partial<ResultFilters>) => onChange({ ...filters, ...patch });
  const st = statusCounts(rows, filters);
  const courts = courtOptions(rows);
  const bounds = yearBounds(rows);
  const years = bounds ? Array.from({ length: bounds[1] - bounds[0] + 1 }, (_, i) => bounds[1] - i) : [];
  const excluded = counts.excluded ?? 0;
  const other = counts.other ?? 0;
  const hidden = (filters.showExcluded ? 0 : excluded) + (filters.showOther ? 0 : other);

  useEffect(() => {
    if (!popover) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !popRef.current?.contains(e.target as Node)) setPopover(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [popover]);

  return (
    <div role="search" aria-label="Filter results" className="flex shrink-0 flex-wrap items-center gap-2">
      <label className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
        <input
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
          placeholder="Search case no., party or court"
          aria-label="Search case number, party, advocate or court"
          className={cn(field, "w-[260px] pl-8")}
        />
      </label>
      <button type="button" className={chipCls(filters.status === "all")} aria-pressed={filters.status === "all"} onClick={() => set({ status: "all" })}>
        All
      </button>
      {st.known && (
        <>
          <button type="button" className={chipCls(filters.status === "pending")} aria-pressed={filters.status === "pending"} onClick={() => set({ status: "pending" })}>
            Pending {st.pending}
          </button>
          <button type="button" className={chipCls(filters.status === "disposed")} aria-pressed={filters.status === "disposed"} onClick={() => set({ status: "disposed" })}>
            Disposed {st.disposed}
          </button>
        </>
      )}
      <select aria-label="Court" value={filters.court} onChange={(e) => set({ court: e.target.value })} className={cn(field, "max-w-[190px]")}>
        <option value="">All courts</option>
        {courts.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
      {bounds && (
        <span className="flex items-center gap-1.5 text-[13px] text-gray-600">
          Year
          <select aria-label="Year from" value={filters.yearFrom ?? ""} onChange={(e) => set({ yearFrom: e.target.value ? Number(e.target.value) : null })} className={field}>
            <option value="">{bounds[0]}</option>
            {[...years].reverse().map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
          to
          <select aria-label="Year to" value={filters.yearTo ?? ""} onChange={(e) => set({ yearTo: e.target.value ? Number(e.target.value) : null })} className={field}>
            <option value="">{bounds[1]}</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </span>
      )}
      <button type="button" className={chipCls(filters.match === "verified")} aria-pressed={filters.match === "verified"} onClick={() => set({ match: filters.match === "verified" ? "all" : "verified" })}>
        Match: Verified
      </button>
      <button type="button" className={chipCls(filters.match === "check")} aria-pressed={filters.match === "check"} onClick={() => set({ match: filters.match === "check" ? "all" : "check" })}>
        Needs a check
      </button>
      <div className="relative ml-auto" ref={popRef}>
        <button type="button" className={chipCls(popover || filters.showExcluded || filters.showOther)} aria-haspopup="dialog" aria-expanded={popover} onClick={() => setPopover((v) => !v)}>
          <Eye className="mr-1 inline h-3.5 w-3.5" />
          Show hidden ({hidden})
        </button>
        {popover && (
          <div role="dialog" aria-label="Hidden rows" className="absolute right-0 z-20 mt-1 w-56 rounded-md border border-gray-200 bg-surface p-3 shadow-card">
            <label className="flex items-center gap-2 py-1 text-[13px]">
              <input type="checkbox" className="h-4 w-4 accent-primary" checked={filters.showExcluded} onChange={(e) => set({ showExcluded: e.target.checked })} />
              Not me list ({excluded})
            </label>
            <label className="flex items-center gap-2 py-1 text-[13px]">
              <input type="checkbox" className="h-4 w-4 accent-primary" checked={filters.showOther} onChange={(e) => set({ showOther: e.target.checked })} />
              Other names ({other})
            </label>
            <p className="mt-1 text-[11px] text-gray-500">Both are hidden by default. Nothing is deleted.</p>
          </div>
        )}
      </div>
    </div>
  );
}
