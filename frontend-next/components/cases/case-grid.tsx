import { CaseCard } from "./case-card";
import type { UrgencyReason } from "@/lib/case-urgency";
import type { Case } from "@/types";

interface CaseGridProps {
  cases: Case[];
  isLoading?: boolean;
  onDelete?: (id: number) => void;
  deletingId?: number;
  /** Case id -> urgency reason badge, e.g. for the "Needs Attention" group. */
  urgencyReasons?: Map<number, UrgencyReason>;
}

export function CaseGrid({ cases, isLoading, onDelete, deletingId, urgencyReasons }: CaseGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-80 bg-gray-200 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  if (cases.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-6xl mb-4">⚖️</div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">
          No cases found
        </h3>
        <p className="text-gray-500">
          Try adjusting your filters or create a new case.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {cases.map((caseItem, i) => (
        <CaseCard
          key={caseItem.id}
          case={caseItem}
          index={i}
          onDelete={onDelete}
          isDeleting={deletingId === caseItem.id}
          urgencyReason={urgencyReasons?.get(caseItem.id)}
        />
      ))}
    </div>
  );
}
