import { Button } from "@/components/ui/button";
import { StatusBadge, PriorityBadge } from "@/components/ui/badge";
import { Share2, MessageSquare, Calendar } from "lucide-react";
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
    <div className="bg-white border-b border-gray-200 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Status and Actions */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <StatusBadge status={caseItem.status} />
            <PriorityBadge priority={caseItem.priority} />
            <span className="text-sm text-gray-500 font-mono">
              {caseItem.case_number}
            </span>
          </div>
          <div className="flex items-center gap-2">
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
        <div className="mb-4">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            {caseItem.title}
          </h1>
          <div className="flex items-center gap-4 text-sm text-gray-600">
            {caseItem.case_type && (
              <span className="capitalize">{caseItem.case_type} Case</span>
            )}
            <span className="flex items-center gap-1">
              <Calendar className="h-4 w-4" />
              Filed: {caseItem.filing_date || "N/A"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
