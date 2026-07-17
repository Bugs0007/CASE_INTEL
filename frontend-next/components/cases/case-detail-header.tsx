import Link from "next/link";
import { Button } from "@/components/ui/button";
import { StatusBadge, PriorityBadge } from "@/components/ui/badge";
import { Share2, MessageSquare, Calendar, ChevronLeft } from "lucide-react";
import type { Case } from "@/types";

interface CaseDetailHeaderProps {
  case: Case;
  onStartChat?: () => void;
}

export function CaseDetailHeader({
  case: caseItem,
  onStartChat,
}: CaseDetailHeaderProps) {
  return (
    <div className="bg-white border-b border-gray-100 px-7 py-5 flex-shrink-0">
      <Link
        href="/cases"
        className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-gray-600 mb-3.5 hover:text-gray-800"
      >
        <ChevronLeft className="h-4 w-4" strokeWidth={1.8} />
        Back to Cases
      </Link>

      {/* Status and Actions */}
      <div className="flex items-center justify-between mb-3.5 flex-wrap gap-2.5">
        <div className="flex items-center gap-2.5 flex-wrap">
          <StatusBadge status={caseItem.status} />
          <PriorityBadge priority={caseItem.priority} />
          <span className="text-[13px] text-gray-400 font-mono">
            {caseItem.case_number}
          </span>
        </div>
        <div className="flex items-center gap-2.5">
          <Button variant="secondary" size="sm">
            <Share2 className="h-4 w-4" />
            Share
          </Button>
          <Button variant="primary" size="sm" onClick={onStartChat}>
            <MessageSquare className="h-4 w-4" />
            Ask AI Assistant
          </Button>
        </div>
      </div>

      {/* Case Title */}
      <h1 className="text-[26px] font-bold text-gray-900 mb-2">
        {caseItem.title}
      </h1>
      <div className="flex items-center gap-4 text-[13px] text-gray-600">
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
