"use client";

import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/card";
import { CaseOptionsMenu } from "@/components/cases/list/case-options-menu";
import { StatusBadge, PriorityBadge } from "@/components/ui/badge";
import { cn, hasPlaceholderTitle, pluralize, staggerDelay, primaryClientContact } from "@/lib/utils";
import type { UrgencyReason } from "@/lib/case-urgency";
import { orderCheckMarker } from "./order-sync-status";
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
  const client = primaryClientContact(caseItem.client_contacts);
  const orderMarker = orderCheckMarker(caseItem);

  return (
    <Card
      onClick={() => router.push(`/cases/${caseItem.id}`)}
      style={staggerDelay(index)}
      className={cn(
        "p-[18px] cursor-pointer transition-all hover:shadow-md hover:-translate-y-0.5 animate-fade-up motion-reduce:animate-none motion-reduce:hover:translate-y-0",
        urgencyReason && "border-status-pending",
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2.5">
        <div className="flex items-center gap-2 flex-wrap">
          {urgencyReason && (
            <span className={`ci-chip ci-chip--${urgencyReason.chip} flex-shrink-0`}>
              {urgencyReason.label}
            </span>
          )}
          {/* Only what is out of the ordinary: an open, medium case stays quiet. */}
          {caseItem.status !== "open" && <StatusBadge status={caseItem.status} />}
          {(caseItem.priority === "high" || caseItem.priority === "critical") && (
            <PriorityBadge priority={caseItem.priority} />
          )}
        </div>
        <CaseOptionsMenu onDelete={() => onDelete?.(caseItem.id)} isDeleting={isDeleting} />
      </div>

      {/* Case number + title + client -- case number is an identifier, so
          it gets the mono treatment (font-mono already present, now points
          at IBM Plex Mono via the tailwind.config remap). */}
      <div className="text-xs text-gray-400 font-mono mb-1">
        {caseItem.case_number}
      </div>
      <h3
        className={cn(
          "text-base font-semibold mb-2 line-clamp-2 leading-snug",
          hasPlaceholderTitle(caseItem) ? "text-gray-400" : "text-gray-900",
        )}
      >
        {hasPlaceholderTitle(caseItem) ? "Untitled matter" : caseItem.title}
      </h3>
      {/* The billed Client when one is linked, else the contact -- each
          labelled, so a contact never reads as a client Billing can't find. */}
      {(caseItem.client_detail || client) && (
        <div className="text-meta text-gray-600 mb-3.5 truncate">
          {caseItem.client_detail ? `Client: ${caseItem.client_detail.name}` : `Contact: ${client?.name}`}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center gap-3.5 pt-3 border-t border-gray-100 text-xs text-gray-400">
        <span>{pluralize(caseItem.document_count, "doc")}</span>
        <span>{pluralize(caseItem.hearing_count, "hearing")}</span>
        {orderMarker && (
          <span className="ci-chip ci-chip--pending ml-auto" data-testid="order-check-marker">
            {orderMarker}
          </span>
        )}
      </div>
    </Card>
  );
}
