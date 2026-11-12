"use client";

import { useState } from "react";
import { SlidersHorizontal, Search } from "lucide-react";
import { Reveal } from "@/components/mobile/primitives";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { Select } from "@/components/ui/select";
import { CaseCombobox } from "./list/case-combobox";
import type { DocCase } from "./list/model";
import type { DocumentType, ProcessingStatus } from "@/types";

interface DocumentFiltersProps {
  /** Cases that have documents, for the case picker. */
  cases: DocCase[];
  caseId: number | null;
  type: DocumentType | null;
  status: ProcessingStatus | null;
  /** How many documents failed processing (shown on the Failed option). */
  failedCount: number;
  onSearchChange: (query: string) => void;
  onCaseChange: (caseId: number | null) => void;
  onTypeChange: (type: DocumentType | null) => void;
  onStatusChange: (status: ProcessingStatus | null) => void;
}

const DOCUMENT_TYPES: DocumentType[] = [
  "court_order",
  "order",
  "pleading",
  "motion",
  "brief",
  "evidence",
  "correspondence",
  "contract",
  "other",
];

function typeLabel(type: DocumentType): string {
  if (type === "court_order") return "From eCourts";
  return type.charAt(0).toUpperCase() + type.slice(1);
}

const PROCESSING_STATUSES: ProcessingStatus[] = [
  "pending",
  "processing",
  "completed",
  "failed",
];

export function DocumentFilters({
  cases,
  caseId,
  type,
  status,
  failedCount,
  onSearchChange,
  onCaseChange,
  onTypeChange,
  onStatusChange,
}: DocumentFiltersProps) {
  const isMobile = useIsMobile();
  // On a phone the three selects fold away behind one Filters button (they
  // stay mounted, so a chosen filter is kept while hidden).
  const [filtersOpen, setFiltersOpen] = useState(false);
  const activeCount = Number(caseId !== null) + Number(type !== null) + Number(status !== null);

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 max-md:p-3">
      <div className="grid grid-cols-1 md:grid-cols-[1.3fr_1.4fr_0.8fr_0.8fr] gap-3 max-md:gap-0">
        {/* Search */}
        <div className="flex items-center gap-2.5 h-10 max-md:h-12 rounded-lg border border-gray-200 px-3">
          <Search className="h-4 w-4 text-gray-400 flex-shrink-0" strokeWidth={1.8} />
          <input
            type="text"
            aria-label="Search documents"
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
        <CaseCombobox cases={cases} value={caseId} onChange={onCaseChange} />

        <Select
          aria-label="Filter by type"
          value={type ?? ""}
          onChange={(e) => onTypeChange((e.target.value as DocumentType) || null)}
        >
          <option value="">All types</option>
          {DOCUMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {typeLabel(t)}
            </option>
          ))}
        </Select>

        <Select
          aria-label="Filter by status"
          value={status ?? ""}
          onChange={(e) => onStatusChange((e.target.value as ProcessingStatus) || null)}
        >
          <option value="">All statuses</option>
          {PROCESSING_STATUSES.map((st) => (
            <option key={st} value={st}>
              {st.charAt(0).toUpperCase() + st.slice(1)}
              {st === "failed" && failedCount > 0 ? ` (${failedCount})` : ""}
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
