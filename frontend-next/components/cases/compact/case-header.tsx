"use client";

import Link from "next/link";
import { Bot, ChevronLeft, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PriorityBadge, StatusBadge } from "@/components/ui/badge";
import { showToast } from "@/components/ui/toaster";
import { useRefreshTracking } from "@/hooks/use-case-tracking";
import { dayMonth } from "@/lib/dashboard/dates";
import { caseFacts, syncState, type SyncTone } from "@/lib/case-page-rows";
import { cn, hasPlaceholderTitle } from "@/lib/utils";
import type { Case } from "@/types";

const DOT: Record<SyncTone, string> = {
  ok: "bg-[var(--ci-listed)]",
  stale: "bg-[var(--ci-warn)]",
  failed: "bg-[var(--ci-seal)]",
  off: "bg-gray-400",
};

interface CaseHeaderProps {
  caseItem: Case;
  /** Opens the Court tracking dialog (the sync status is the button). */
  onOpenTracking: () => void;
  /** Opens the Case details dialog. */
  onOpenDetails: () => void;
  /** Opens Edit Details, for a case with no real title yet. */
  onEditDetails: () => void;
  onCaseBot: () => void;
  /** The sync button, so focus can come back to it. */
  trackingButtonRef?: React.RefObject<HTMLButtonElement | null>;
}

/** One 56px row: back, status, priority, case number, title; and on the
 * right the court-tracking sync status, Refresh and Case Bot. */
export function CaseHeaderRow({
  caseItem,
  onOpenTracking,
  onOpenDetails,
  onEditDetails,
  onCaseBot,
  trackingButtonRef,
}: CaseHeaderProps) {
  const refresh = useRefreshTracking(caseItem.id);
  const sync = syncState(caseItem);
  const untitled = hasPlaceholderTitle(caseItem);

  async function handleRefresh() {
    try {
      const result = await refresh.mutateAsync(false);
      if (result.rate_limited) {
        showToast.error("Refresh limited", "This case was checked recently. Try again in a bit.");
      } else {
        showToast.success(
          "Tracking refreshed",
          result.new_hearing_dates && result.new_hearing_dates.length > 0
            ? `${result.new_hearing_dates.length} new hearing date(s) found.`
            : "No changes since last check.",
        );
      }
    } catch {
      showToast.error("Refresh failed", "Could not reach the court portal. Please try again later.");
    }
  }

  return (
    <div className="flex h-14 flex-shrink-0 items-center gap-3 border-b border-gray-200 bg-surface px-5">
      <Link
        href="/cases"
        aria-label="Back to cases"
        title="Back to cases"
        className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded border border-[var(--ci-ink-14)] text-gray-700 hover:border-[var(--ci-ink)]"
      >
        <ChevronLeft className="h-4 w-4" />
      </Link>
      <div className="flex flex-shrink-0 items-center gap-2">
        <StatusBadge status={caseItem.status} />
        <PriorityBadge priority={caseItem.priority} />
      </div>
      <span className="hidden flex-shrink-0 font-mono text-[13px] text-gray-500 sm:inline">{caseItem.case_number}</span>
      {untitled ? (
        <div className="flex min-w-0 items-center gap-2">
          <h1 className="truncate font-serif text-[22px] font-bold text-gray-400">Untitled matter</h1>
          <button type="button" onClick={onEditDetails} className="flex-shrink-0 text-xs font-semibold text-gray-700 underline">
            Add a title
          </button>
        </div>
      ) : (
        <h1 className="min-w-0 truncate font-serif text-[22px] font-bold leading-none text-gray-900" title={caseItem.title}>
          {caseItem.title}
        </h1>
      )}
      {caseItem.disposal && (
        <button
          type="button"
          onClick={onOpenDetails}
          className="ci-chip ci-chip--pending flex-shrink-0 cursor-pointer"
          title="The case looks disposed of. Review it in the case details."
        >
          Looks disposed
        </button>
      )}

      <div className="ml-auto flex flex-shrink-0 items-center gap-2.5">
        <button
          ref={trackingButtonRef}
          type="button"
          onClick={onOpenTracking}
          className="hidden items-center gap-2 text-[13px] text-gray-600 hover:text-gray-900 md:flex"
          title="Open court tracking"
        >
          <span className={cn("h-2 w-2 rounded-full", DOT[sync.tone])} aria-hidden="true" />
          {sync.label}
        </button>
        {caseItem.tracking_enabled && (
          <Button variant="secondary" size="sm" onClick={handleRefresh} disabled={refresh.isPending}>
            {refresh.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            Refresh
          </Button>
        )}
        <Button variant="primary" size="sm" onClick={onCaseBot}>
          <Bot className="h-4 w-4" />
          Case Bot
        </Button>
      </div>
    </div>
  );
}

function Cell({ label, children, last }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <div className={cn("flex min-w-0 flex-col justify-center px-4", !last && "border-r border-gray-200")}>
      <span className="font-mono text-[11px] uppercase leading-none tracking-[0.08em] text-gray-500">{label}</span>
      <span className="mt-1 min-w-0 truncate text-[13px] font-semibold leading-tight text-gray-900">{children}</span>
    </div>
  );
}

/** Six facts in 46px: court, stage, your side, client, filed and CNR. */
export function FactsStrip({
  caseItem,
  onSetSide,
  onOpenDetails,
}: {
  caseItem: Case;
  onSetSide: () => void;
  onOpenDetails: () => void;
}) {
  const f = caseFacts(caseItem);
  return (
    <div className="grid h-[46px] flex-shrink-0 grid-cols-[repeat(6,minmax(0,1fr))_auto] border-b border-gray-200 bg-surface max-md:hidden">
      <Cell label="Court">{f.court}</Cell>
      <Cell label="Stage">{f.stage}</Cell>
      <Cell label="Your side">
        {f.side ? (
          f.side
        ) : (
          <span className="flex items-center gap-2">
            <span className="ci-chip ci-chip--pending">Not set</span>
            <button type="button" onClick={onSetSide} className="font-semibold underline">
              Set
            </button>
          </span>
        )}
      </Cell>
      <Cell label="Client">{f.client}</Cell>
      <Cell label="Filed">{f.filed ? `${dayMonth(f.filed)} ${f.filed.slice(0, 4)}` : "—"}</Cell>
      <Cell label="CNR" last>
        <span className="font-mono">{f.cnr}</span>
      </Cell>
      <button
        type="button"
        onClick={onOpenDetails}
        className="flex items-center gap-1 border-l border-gray-200 px-4 text-[13px] font-semibold text-gray-700 hover:text-gray-900"
      >
        All details
        <ChevronRight className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
