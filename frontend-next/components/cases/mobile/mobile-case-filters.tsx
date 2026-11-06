"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CaseStatus } from "@/types";

const STATUS_TABS = [
  { key: "all" as const, label: "All cases" },
  { key: "open" as const, label: "Open" },
  { key: "closed" as const, label: "Closed" },
  { key: "archived" as const, label: "Archived" },
];

/** The status filter as a row of tabs with an underline that glides between
 * them (a transform: translateX + scaleX), for the sticky strip under the
 * phone's top bar. */
export function MobileStatusTabs({
  active,
  onChange,
}: {
  active: CaseStatus | "all";
  onChange: (status: CaseStatus | "all") => void;
}) {
  const refs = useRef<Partial<Record<string, HTMLButtonElement>>>({});
  const [mark, setMark] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const el = refs.current[active];
    if (el) setMark({ left: el.offsetLeft, width: el.offsetWidth });
  }, [active]);

  return (
    <div role="tablist" aria-label="Case status" className="ci-hscroll relative h-full items-stretch !gap-0 px-2">
      {STATUS_TABS.map((tab) => (
        <button
          key={tab.key}
          ref={(el) => {
            refs.current[tab.key] = el ?? undefined;
          }}
          type="button"
          role="tab"
          aria-selected={active === tab.key}
          onClick={() => onChange(tab.key)}
          className={cn(
            "h-full px-4 text-[13.5px] font-semibold transition-colors",
            active === tab.key ? "text-gray-900" : "text-gray-500",
          )}
        >
          {tab.label}
        </button>
      ))}
      {mark && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute bottom-0 left-0 h-[3px] w-[100px] origin-left bg-[var(--ci-ink)] transition-transform duration-300 ease-[cubic-bezier(0.2,0.8,0.2,1)] motion-reduce:transition-none"
          style={{ transform: `translateX(${mark.left}px) scaleX(${mark.width / 100})` }}
        />
      )}
    </div>
  );
}

/** A large search field for the top of the Cases list. */
export function MobileCaseSearch({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return (
    <div className="flex h-12 items-center gap-2.5 rounded-[3px] border border-gray-200 bg-surface px-3 focus-within:border-[var(--ci-ink)]">
      <Search className="h-[18px] w-[18px] flex-shrink-0 text-gray-400" strokeWidth={1.8} aria-hidden="true" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search by case, client or party"
        aria-label="Search cases"
        enterKeyHint="search"
        className="min-w-0 flex-1 bg-transparent text-gray-800 outline-none placeholder:text-gray-400 [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange("")}
          className="flex h-8 w-8 flex-shrink-0 animate-pop-in items-center justify-center rounded-full bg-gray-100 text-gray-500 motion-reduce:animate-none"
        >
          <X className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
