"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge, PriorityBadge } from "@/components/ui/badge";
import { MoreVertical, Trash2 } from "lucide-react";
import { cn, staggerDelay } from "@/lib/utils";
import type { UrgencyReason } from "@/lib/case-urgency";
import type { Case } from "@/types";

interface CaseCardProps {
  case: Case;
  onDelete?: (id: number) => void;
  isDeleting?: boolean;
  /** "Needs attention this week" reason badge — same treatment as the
   * Dashboard's Cases-by-urgency section. Omit for cases that don't need
   * attention. */
  urgencyReason?: UrgencyReason;
  /** Position in the grid, for a stagger-in delay on first mount. */
  index?: number;
}

export function CaseCard({ case: caseItem, onDelete, isDeleting, urgencyReason, index = 0 }: CaseCardProps) {
  const router = useRouter();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isMenuOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isMenuOpen]);

  return (
    <Card
      onClick={() => router.push(`/cases/${caseItem.id}`)}
      style={staggerDelay(index)}
      className={cn(
        "p-[18px] cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 animate-fade-up motion-reduce:animate-none motion-reduce:hover:translate-y-0",
        urgencyReason && "border-[#f0d9bb]",
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2.5">
        <div className="flex items-center gap-2 flex-wrap">
          {urgencyReason && (
            <span
              className={`inline-flex items-center h-5 px-2 rounded-full text-[11px] font-semibold ${urgencyReason.className}`}
            >
              {urgencyReason.label}
            </span>
          )}
          <StatusBadge status={caseItem.status} />
          <PriorityBadge priority={caseItem.priority} />
        </div>
        <div className="relative flex-shrink-0" ref={menuRef}>
          <Button
            variant="ghost"
            size="sm"
            className="p-1 h-11 w-11 md:h-8 md:w-8"
            onClick={(e) => {
              e.stopPropagation();
              setIsMenuOpen((open) => !open);
            }}
            aria-haspopup="true"
            aria-expanded={isMenuOpen}
            aria-label="Case options"
          >
            <MoreVertical className="h-4 w-4" />
          </Button>
          {isMenuOpen && (
            <div
              role="menu"
              onClick={(e) => e.stopPropagation()}
              className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-100 py-1 z-10"
            >
              <button
                role="menuitem"
                disabled={isDeleting}
                onClick={() => {
                  setIsMenuOpen(false);
                  onDelete?.(caseItem.id);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-[#fdecec] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <Trash2 className="h-4 w-4" />
                {isDeleting ? "Deleting..." : "Delete Case"}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Case number + title + client */}
      <div className="text-xs text-gray-400 font-mono mb-1">
        {caseItem.case_number}
      </div>
      <h3 className="text-base font-semibold text-gray-900 mb-2 line-clamp-2 leading-snug">
        {caseItem.title}
      </h3>
      <div className="text-meta text-gray-600 mb-3.5">{caseItem.client_name}</div>

      {/* Footer */}
      <div className="flex items-center gap-3.5 pt-3 border-t border-[#f2f3f5] text-xs text-gray-400">
        <span>{caseItem.document_count} docs</span>
        <span>{caseItem.hearing_count} hearings</span>
      </div>
    </Card>
  );
}
