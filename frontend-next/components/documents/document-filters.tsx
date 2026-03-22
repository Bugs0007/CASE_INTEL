import { useState, useMemo } from "react";
import { SearchInput } from "@/components/ui/input";
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
  "pleading",
  "motion",
  "brief",
  "evidence",
  "correspondence",
  "contract",
  "order",
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

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Search */}
        <SearchInput
          placeholder="Search documents..."
          onChange={(e) => onSearchChange(e.target.value)}
        />

        {/* Case Filter */}
        <Select
          onChange={(e) =>
            onCaseChange(e.target.value ? Number(e.target.value) : null)
          }
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
          onChange={(e) =>
            onTypeChange((e.target.value as DocumentType) || null)
          }
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
          onChange={(e) =>
            onStatusChange((e.target.value as ProcessingStatus) || null)
          }
        >
          <option value="">All Statuses</option>
          {PROCESSING_STATUSES.map((status) => (
            <option key={status} value={status}>
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}
