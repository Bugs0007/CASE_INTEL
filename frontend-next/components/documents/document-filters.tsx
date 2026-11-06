"use client";

import { useState } from "react";
import { SlidersHorizontal, Search } from "lucide-react";
import { Reveal } from "@/components/mobile/primitives";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { Select } from "@/components/ui/select";
import { useCases } from "@/hooks/use-cases";
import type { DocumentType, ProcessingStatus } from "@/types";

interface DocumentFiltersProps {
  onSearchChange: (query: string) => void;
  onCaseChange: (caseId: number | null) => void;
  onTypeChange: (type: DocumentType | null) => void;
  onStatusChange: (status: ProcessingStatus | null) => void;
}

const DOCUMENT_TYPES: DocumentType[] = [
  "motion",
  "evidence",
  "correspondence",
  "contract",
  "other",
];

const PROCESSING_STATUSES: ProcessingStatus[] = [
  "pending",
  "processing",
  "completed",
  "failed",
];

export function DocumentFilters({
  onSearchChange,
  onCaseChange,
  onTypeChange,
  onStatusChange,
}: DocumentFiltersProps) {
  const { data: cases = [] } = useCases();
  const isMobile = useIsMobile();
  // On a phone the three selects fold away behind one Filters button (they
  // stay mounted, so a chosen filter is kept while hidden).
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [active, setActive] = useState({ case: false, type: false, status: false });
  const activeCount = Number(active.case) + Number(active.type) + Number(active.status);

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 max-md:p-3">
      <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr_1fr_1fr] gap-3 max-md:gap-0">
        {/* Search */}
        <div className="flex items-center gap-2.5 h-10 max-md:h-12 rounded-lg border border-gray-200 px-3">
          <Search className="h-4 w-4 text-gray-400 flex-shrink-0" strokeWidth={1.8} />
          <input
            type="text"
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search documents…"
            className="flex-1 min-w-0 bg-transparent text-sm text-gray-800 placeholder:text-gray-400 outline-none"
          />
          {isMobile && (
            <button
              type="button"
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen((v) => !v)}
              className="-mr-2 flex h-10 flex-shrink-0 items-center gap-1.5 rounded-md px-2.5 text-[13px] font-semibold text-gray-700"
            >
              <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
              Filters
              {activeCount > 0 && (
                <span
                  key={activeCount}
                  className="flex h-5 min-w-5 animate-pop-in items-center justify-center rounded-full bg-[var(--ci-ink)] px-1 text-[11px] text-[color:var(--ci-paper)] motion-reduce:animate-none"
                >
                  {activeCount}
                </span>
              )}
            </button>
          )}
        </div>

        <FiltersWrap mobile={isMobile} open={filtersOpen}>
        {/* Case Filter */}
        <Select
          onChange={(e) => {
            setActive((a) => ({ ...a, case: !!e.target.value }));
            onCaseChange(e.target.value ? Number(e.target.value) : null);
          }}
        >
          <option value="">All Cases</option>
          {cases.map((caseItem) => (
            <option key={caseItem.id} value={caseItem.id}>
              {caseItem.case_number} - {caseItem.title}
            </option>
          ))}
        </Select>

        {/* Type Filter */}
        <Select
          onChange={(e) => {
            setActive((a) => ({ ...a, type: !!e.target.value }));
            onTypeChange((e.target.value as DocumentType) || null);
          }}
        >
          <option value="">All Types</option>
          {DOCUMENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type.charAt(0).toUpperCase() + type.slice(1)}
            </option>
          ))}
        </Select>

        {/* Status Filter */}
        <Select
          onChange={(e) => {
            setActive((a) => ({ ...a, status: !!e.target.value }));
            onStatusChange((e.target.value as ProcessingStatus) || null);
          }}
        >
          <option value="">All Statuses</option>
          {PROCESSING_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </option>
          ))}
        </Select>
        </FiltersWrap>
      </div>
    </div>
  );
}

/** Desktop: the selects are plain cells of the filter grid. Phone: they sit
 * in a folding panel under the search box. */
function FiltersWrap({ mobile, open, children }: { mobile: boolean; open: boolean; children: React.ReactNode }) {
  if (!mobile) return <>{children}</>;
  return (
    <Reveal open={open}>
      <div className="grid gap-3 pt-3">{children}</div>
    </Reveal>
  );
}
