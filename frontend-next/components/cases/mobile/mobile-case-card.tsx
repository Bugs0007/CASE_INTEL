"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, ExternalLink, MoreVertical, Trash2 } from "lucide-react";
import { DateTile } from "@/components/mobile/primitives";
import { BottomSheet } from "@/components/ui/bottom-sheet";
import { hearingDayKey } from "@/lib/calendar";
import type { UrgencyReason } from "@/lib/case-urgency";
import { istDayKey } from "@/lib/dashboard/dates";
import { dueUrgency, relativeDay } from "@/lib/mobile-format";
import { cn, hasPlaceholderTitle, pluralize, staggerDelay } from "@/lib/utils";
import { orderCheckMarker } from "@/components/cases/order-sync-status";
import type { Case } from "@/types";

/** A case as one compact card for a phone: the number and any status that
 * matters, the title, the next hearing as a date tile with how far away it is,
 * and the counts. The whole card opens the case; the ⋯ opens a sheet.
 *
 * Only what is out of the ordinary is shown as a chip (high or critical
 * priority, a case that is not open), so a plain open case stays quiet. */
export function MobileCaseCard({
  case: caseItem,
  index = 0,
  urgencyReason,
  onDelete,
  isDeleting,
}: {
  case: Case;
  index?: number;
  urgencyReason?: UrgencyReason;
  onDelete?: (id: number) => void;
  isDeleting?: boolean;
}) {
  const [sheetOpen, setSheetOpen] = useState(false);
  const today = istDayKey();
  const nextDay = caseItem.next_hearing_date ? hearingDayKey(caseItem.next_hearing_date) : null;
  const upcoming = nextDay !== null && nextDay >= today;
  const orderMarker = orderCheckMarker(caseItem);
  const untitled = hasPlaceholderTitle(caseItem);
  const loud = caseItem.priority === "critical" || caseItem.priority === "high";
  const tone = !upcoming ? "none" : dueUrgency(nextDay, today) === "none" ? "ink" : "pending";

  return (
    <li
      style={staggerDelay(index, 45, 10)}
      className={cn(
        "relative animate-rise-in rounded-[3px] border bg-surface shadow-card motion-reduce:animate-none",
        urgencyReason ? "border-status-pending" : "border-[var(--ci-ink-14)]",
      )}
    >
      {/* A bar down the left edge carries priority without a chip. */}
      <span
        aria-hidden="true"
        className={cn(
          "absolute bottom-0 left-0 top-0 w-[3px] rounded-l-[3px]",
          caseItem.priority === "critical" && "bg-[var(--ci-seal)]",
          caseItem.priority === "high" && "bg-[var(--ci-warn)]",
        )}
      />
      <Link
        href={`/cases/${caseItem.id}`}
        aria-label={`Open case ${untitled ? caseItem.case_number : caseItem.title}`}
        className="block py-3 pl-4 pr-14 [--press-scale:0.985]"
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-[11.5px] text-gray-500">{caseItem.case_number}</span>
          {urgencyReason && <span className={`ci-chip ci-chip--${urgencyReason.chip}`}>{urgencyReason.label}</span>}
          {caseItem.status !== "open" && <span className="ci-chip ci-chip--none">{caseItem.status}</span>}
          {loud && !urgencyReason && (
            <span className={cn("ci-chip", caseItem.priority === "critical" ? "ci-chip--alert" : "ci-chip--pending")}>
              {caseItem.priority}
            </span>
          )}
        </div>
        <h3
          className={cn(
            "mt-1 line-clamp-2 !font-sans !text-[15.5px] !font-semibold !leading-snug !tracking-normal",
            untitled ? "text-gray-400" : "text-gray-900",
          )}
        >
          {untitled ? "Untitled matter" : caseItem.title}
        </h3>
        <div className="mt-0.5 truncate text-[12.5px] text-gray-600">
          {caseItem.client_detail ? caseItem.client_detail.name : caseItem.client_contacts[0]?.name || "No client yet"}
        </div>

        <div className="mt-2.5 flex items-center gap-3">
          {nextDay ? (
            <>
              <DateTile day={nextDay} tone={tone} index={index} className="!h-[50px] !w-[44px]" />
              <div className="min-w-0">
                <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-gray-500">
                  {upcoming ? "Next hearing" : "Last listed"}
                </div>
                <div className="text-[14px] font-semibold text-gray-900">{relativeDay(nextDay, today)}</div>
              </div>
            </>
          ) : (
            <div className="text-[13px] text-gray-500">No hearing scheduled</div>
          )}
          <div className="ml-auto self-end text-right text-[11.5px] leading-tight text-gray-500">
            <div>{pluralize(caseItem.document_count, "doc")}</div>
            <div>{pluralize(caseItem.hearing_count, "hearing")}</div>
          </div>
        </div>

        {orderMarker && (
          <div className="mt-2 flex items-center gap-1.5 text-[12px] text-[color:var(--ci-warn)]" data-testid="order-check-marker">
            <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
            <span className="truncate">{orderMarker}</span>
          </div>
        )}
      </Link>

      <button
        type="button"
        aria-label="Case options"
        aria-haspopup="dialog"
        onClick={() => setSheetOpen(true)}
        className="absolute right-1 top-1 flex h-11 w-11 items-center justify-center rounded-full text-gray-500"
      >
        <MoreVertical className="h-4 w-4" />
      </button>

      <BottomSheet
        open={sheetOpen}
        onClose={() => setSheetOpen(false)}
        label="Case options"
        title={untitled ? caseItem.case_number : caseItem.title}
      >
        <ul className="py-1">
          <li>
            <Link href={`/cases/${caseItem.id}`} className="flex h-14 items-center gap-3 px-4 text-[15px] font-semibold text-gray-900">
              <ExternalLink className="h-5 w-5 text-gray-500" aria-hidden="true" />
              Open case
            </Link>
          </li>
          {onDelete && (
            <li>
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => {
                  setSheetOpen(false);
                  onDelete(caseItem.id);
                }}
                className="flex h-14 w-full items-center gap-3 px-4 text-[15px] font-semibold text-destructive disabled:opacity-50"
              >
                <Trash2 className="h-5 w-5" aria-hidden="true" />
                {isDeleting ? "Deleting…" : "Delete case"}
              </button>
            </li>
          )}
        </ul>
      </BottomSheet>
    </li>
  );
}
