"use client";

import { Loader2, NotebookPen, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PurposePill, formatPlainDate, relativeDayLabel } from "@/components/cases/daily-status-card";
import type { HearingBusinessCheck } from "@/hooks/use-hearing-business";
import { oneLine, type HearingBusinessInfo } from "@/lib/hearing-business";
import { cn } from "@/lib/utils";
import type { DailyStatusEntry } from "@/types/daily-status";

/** What happened at one hearing: the court's recorded business, the next
 * purpose and the next date. The same section is the phone's hearing sheet
 * content and the desktop row's expansion. */

/** A line of a row's list entering: starts after the sheet or row has. */
const enter = (step: number) => ({ animationDelay: `${140 + step * 60}ms` });

function Label({ children }: { children: string }) {
  return <dt className="text-xs font-semibold uppercase tracking-wide text-gray-500">{children}</dt>;
}

/** "What happened is not saved yet" with the Check now button, or the line
 * that says the check is under way. */
function NotSavedYet({ check }: { check: HearingBusinessCheck }) {
  return (
    <div>
      <p className="text-[13.5px] text-gray-600">What happened is not saved yet.</p>
      {check.checking ? (
        <p role="status" className="mt-1.5 flex items-center gap-1.5 text-[13px] text-gray-600">
          <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
          Checking, this takes a minute
        </p>
      ) : (
        <>
          {check.checkedSince && (
            <p className="mt-1 text-xs text-gray-500">
              Still not saved. Each check saves only the few newest days, so try again in a few minutes.
            </p>
          )}
          {check.canCheck && (
            <Button variant="secondary" size="sm" className="mt-1.5" onClick={check.request}>
              Check now
            </Button>
          )}
        </>
      )}
      {check.note && (
        <p role="status" className="mt-1.5 text-xs text-status-pending">
          {check.note}
        </p>
      )}
    </div>
  );
}

function EntryBody({ entry, inline }: { entry: DailyStatusEntry; inline: boolean }) {
  const hasNext = !!entry.next_purpose || !!entry.next_hearing_date;
  return (
    <>
      {entry.business_text ? (
        <p
          className={cn(
            "whitespace-pre-line break-words text-gray-900",
            inline ? "text-[13.5px] leading-snug" : "text-[15px] leading-relaxed",
          )}
        >
          {entry.business_text}
        </p>
      ) : (
        <p className="text-sm italic text-gray-500">The court recorded no business for this date.</p>
      )}
      {hasNext && (
        <dl
          className={cn(
            "border-t border-gray-200",
            // Inline (a desktop row) the two facts share a line to keep the row short.
            inline ? "mt-2 flex flex-wrap items-center gap-x-8 gap-y-1.5 pt-2" : "mt-3 space-y-2 pt-2.5",
          )}
        >
          {entry.next_purpose && (
            <div
              className={cn(
                "flex items-center gap-3 animate-fade-up motion-reduce:animate-none",
                !inline && "justify-between",
              )}
              style={enter(1)}
            >
              <Label>Next purpose</Label>
              <dd>
                <PurposePill purpose={entry.next_purpose} />
              </dd>
            </div>
          )}
          {entry.next_hearing_date && (
            <div
              className={cn(
                "flex items-baseline gap-3 animate-fade-up motion-reduce:animate-none",
                !inline && "justify-between",
              )}
              style={enter(2)}
            >
              <Label>Next hearing</Label>
              <dd className="text-right text-sm text-gray-900">
                <span className="font-semibold">{formatPlainDate(entry.next_hearing_date)}</span>
                <span className="ml-1.5 text-gray-500">· {relativeDayLabel(entry.next_hearing_date)}</span>
              </dd>
            </div>
          )}
        </dl>
      )}
    </>
  );
}

export interface HearingBusinessSectionProps {
  info: HearingBusinessInfo;
  check: HearingBusinessCheck;
  /** Read the entries again, after a failed read. */
  onReload?: () => void;
  /** "sheet" (default) is the roomy layout of a phone sheet or a dialog;
   * "inline" is the tighter one under a desktop row. */
  variant?: "sheet" | "inline";
  className?: string;
}

/** The "What happened" section of one hearing. Draws nothing when there is
 * nothing to say: not a district case, or a hearing still ahead. */
export function HearingBusinessSection({ info, check, onReload, variant = "sheet", className }: HearingBusinessSectionProps) {
  if (info.kind === "off" || info.kind === "none") return null;

  let body;
  switch (info.kind) {
    case "loading":
      body = (
        <div role="status" aria-label="Loading what happened" className="space-y-2">
          <div className="h-3 w-full animate-pulse rounded bg-gray-200 motion-reduce:animate-none" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-gray-200 motion-reduce:animate-none" />
        </div>
      );
      break;
    case "error":
      body = (
        <div className="text-sm text-gray-700">
          <p>We couldn&apos;t load what the court recorded.</p>
          {onReload && (
            <button
              type="button"
              onClick={onReload}
              className="mt-0.5 inline-flex min-h-[44px] items-center gap-1.5 font-medium text-blue-700 md:min-h-[32px]"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Try again
            </button>
          )}
        </div>
      );
      break;
    case "entry":
      body = <EntryBody entry={info.entry} inline={variant === "inline"} />;
      break;
    case "missing":
      body = <NotSavedYet check={check} />;
      break;
    case "unlisted":
      body = <p className="text-[13.5px] text-gray-600">The court lists no daily status for this date.</p>;
      break;
  }

  return (
    <section
      // A new state (loaded, saved after a check) enters afresh.
      key={info.kind}
      aria-label="What happened"
      data-testid="hearing-business"
      data-state={info.kind}
      style={{ animationDelay: "120ms" }}
      className={cn(
        "mt-3 animate-rise-in rounded-lg border border-gray-100 bg-gray-50 px-3 py-2.5 motion-reduce:animate-none",
        className,
      )}
    >
      <h3 className="mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.1em] text-gray-500">What happened</h3>
      {body}
    </section>
  );
}

/** One muted line under a hearing row on a phone: a note icon and the first
 * of what the court recorded. Shows that this hearing has a record. */
export function HearingBusinessPreview({ entry }: { entry: DailyStatusEntry }) {
  const text = oneLine(entry.business_text);
  return (
    <span data-testid="hearing-business-preview" className="mt-0.5 flex items-center gap-1 text-[12px] text-gray-500">
      <NotebookPen className="h-3 w-3 flex-shrink-0" aria-hidden="true" />
      <span className="min-w-0 truncate">{text || "No business recorded"}</span>
    </span>
  );
}
