import { Search } from "lucide-react";
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

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4">
      <div className="grid grid-cols-1 md:grid-cols-[1.4fr_1fr_1fr_1fr] gap-3">
        {/* Search */}
        <div className="flex items-center gap-2.5 h-10 rounded-lg border border-gray-200 px-3">
          <Search className="h-4 w-4 text-gray-400 flex-shrink-0" strokeWidth={1.8} />
          <input
            type="text"
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search documents…"
            className="flex-1 min-w-0 bg-transparent text-sm text-gray-800 placeholder:text-gray-400 outline-none"
          />
        </div>

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
