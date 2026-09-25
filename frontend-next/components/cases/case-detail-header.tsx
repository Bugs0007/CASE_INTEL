import Link from "next/link";
import { Button } from "@/components/ui/button";
import { StatusBadge, PriorityBadge } from "@/components/ui/badge";
import { Bot, Calendar, ChevronLeft, Pencil } from "lucide-react";
import { hasPlaceholderTitle } from "@/lib/utils";
import type { Case } from "@/types";

interface CaseDetailHeaderProps {
  case: Case;
  onToggleChat?: () => void;
  /** Opens Edit Details -- offered when the case has no real title yet. */
  onEditDetails?: () => void;
}

export function CaseDetailHeader({
  case: caseItem,
  onToggleChat,
  onEditDetails,
}: CaseDetailHeaderProps) {
  const untitled = hasPlaceholderTitle(caseItem);
  // The header stays put while the page scrolls under it, so on a phone
  // every line here is a line of case the advocate can't see: tighter
  // spacing, a smaller two-line title, and the filing date left to Case
  // Overview below `sm`.
  return (
    <div className="bg-white border-b border-gray-100 px-4 sm:px-7 py-3 sm:py-5 flex-shrink-0">
      <Link
        href="/cases"
        className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-gray-600 mb-2 sm:mb-3.5 hover:text-gray-800"
      >
        <ChevronLeft className="h-4 w-4" strokeWidth={1.8} />
        Back to Cases
      </Link>

      {/* Status and Actions */}
      <div className="flex items-center justify-between mb-2 sm:mb-3.5 flex-wrap gap-2.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <StatusBadge status={caseItem.status} />
          <PriorityBadge priority={caseItem.priority} />
          <span className="text-[13px] text-gray-400 font-mono">
            {caseItem.case_number}
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          <Button variant="primary" size="sm" onClick={onToggleChat}>
            <Bot className="h-4 w-4" />
            Case Bot
          </Button>
        </div>
      </div>

      {/* Case Title */}
      {untitled ? (
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <h1 className="text-[22px] sm:text-[26px] font-bold text-gray-400">Untitled matter</h1>
          {onEditDetails && (
            <Button variant="secondary" size="sm" onClick={onEditDetails}>
              <Pencil className="h-3.5 w-3.5" />
              Add a title
            </Button>
          )}
          <span className="basis-full text-xs text-gray-500">
            Client emails use the case number until the matter has a title.
          </span>
        </div>
      ) : (
        <h1
          className="text-[22px] sm:text-[26px] leading-tight font-bold text-gray-900 sm:mb-2 line-clamp-2 sm:line-clamp-none"
          title={caseItem.title}
        >
          {caseItem.title}
        </h1>
      )}
      <div className="hidden sm:flex items-center gap-4 text-[13px] text-gray-600">
        {caseItem.case_type && (
          <span className="capitalize">{caseItem.case_type} Case</span>
        )}
        <span className="flex items-center gap-1">
          <Calendar className="h-3.5 w-3.5" strokeWidth={1.8} />
          Filed: {caseItem.filing_date || "N/A"}
        </span>
      </div>
    </div>
  );
}
