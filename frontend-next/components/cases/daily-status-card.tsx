"use client";

import { useState } from "react";
import { ChevronDown, Gavel, RefreshCw } from "lucide-react";
import { Card } from "@/components/ui/card";
import { useDailyStatus } from "@/hooks/use-daily-status";
import { plainDayKey } from "@/lib/calendar";
import { daysUntilDate } from "@/lib/tasks";
import { cn, staggerDelay } from "@/lib/utils";
import type { DailyStatusEntry } from "@/types/daily-status";

/** District Courts "Daily Status" (Business on Date) for one case: what the
 * court recorded at each hearing and what comes next. Mobile first: the
 * latest hearing as a compact card, earlier ones as an expandable timeline.
 *
 * Not mounted anywhere yet -- the case page places it. */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** Above this many characters the business text starts clamped. */
const LONG_TEXT = 140;

/** A plain "YYYY-MM-DD" as its parts, without any timezone round trip. */
function dateParts(iso: string): { day: number; month: string; year: number } | null {
  const [year, month, day] = plainDayKey(iso).split("-").map(Number);
  if (!year || !month || !day) return null;
  return { day, month: MONTHS[month - 1] ?? "", year };
}

export function formatPlainDate(iso: string | null): string {
  if (!iso) return "";
  const parts = dateParts(iso);
  return parts ? `${parts.day} ${parts.month} ${parts.year}` : "";
}

/** "Today" / "Tomorrow" / "In 13 days" / "2 days ago". */
export function relativeDayLabel(iso: string): string {
  const days = daysUntilDate(plainDayKey(iso));
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  if (days < 0) return `${-days} days ago`;
  return `In ${days} days`;
}

/** Pill colour by the kind of next step the court set. */
export function purposeTone(purpose: string): string {
  const p = purpose.toLowerCase();
  if (/stay|injunction|interim|urgent/.test(p)) return "bg-amber-100 text-amber-900 ring-amber-200";
  if (/judg|order|disposal|pronounce/.test(p)) return "bg-violet-100 text-violet-900 ring-violet-200";
  if (/evidence|exam|witness|trial/.test(p)) return "bg-sky-100 text-sky-900 ring-sky-200";
  if (/argument|hearing/.test(p)) return "bg-emerald-100 text-emerald-900 ring-emerald-200";
  return "bg-slate-100 text-slate-800 ring-slate-200";
}

function DateChip({ iso, size = "lg" }: { iso: string; size?: "lg" | "sm" }) {
  const parts = dateParts(iso);
  if (!parts) return null;
  const big = size === "lg";
  return (
    <div
      aria-hidden="true"
      className={cn(
        "flex flex-shrink-0 flex-col items-center justify-center rounded-xl bg-slate-900 text-white",
        "animate-pop-in motion-reduce:animate-none",
        big ? "h-16 w-14" : "h-11 w-10",
      )}
    >
      <span className={cn("font-semibold leading-none tabular-nums", big ? "text-2xl" : "text-base")}>
        {parts.day}
      </span>
      <span className={cn("mt-0.5 uppercase tracking-wide text-slate-300", big ? "text-[11px]" : "text-[10px]")}>
        {parts.month}
      </span>
    </div>
  );
}

export function PurposePill({ purpose }: { purpose: string }) {
  if (!purpose) return null;
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset",
        purposeTone(purpose),
      )}
    >
      {purpose}
    </span>
  );
}

function BusinessText({ text, clampLines }: { text: string; clampLines: 2 | 3 }) {
  const [open, setOpen] = useState(false);
  if (!text) {
    return <p className="text-sm italic text-gray-500">The court recorded no business for this date.</p>;
  }
  const long = text.length > LONG_TEXT;
  return (
    <div>
      <p
        className={cn(
          "whitespace-pre-line text-[15px] leading-relaxed text-gray-800",
          long && !open && (clampLines === 3 ? "line-clamp-3" : "line-clamp-2"),
        )}
      >
        {text}
      </p>
      {long && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="mt-1 min-h-[44px] text-sm font-medium text-blue-700 underline-offset-2 hover:underline sm:min-h-0"
        >
          {open ? "Show less" : "Read more"}
        </button>
      )}
    </div>
  );
}

function NextHearing({ entry }: { entry: DailyStatusEntry }) {
  if (!entry.next_hearing_date && !entry.next_purpose) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 rounded-lg bg-gray-50 px-3 py-2">
      <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">Next</span>
      <PurposePill purpose={entry.next_purpose} />
      {entry.next_hearing_date && (
        <span className="text-sm text-gray-800">
          <span className="font-semibold">{formatPlainDate(entry.next_hearing_date)}</span>
          <span className="ml-1.5 text-gray-500">· {relativeDayLabel(entry.next_hearing_date)}</span>
        </span>
      )}
    </div>
  );
}

function LatestEntry({ entry }: { entry: DailyStatusEntry }) {
  return (
    <article
      aria-label={`Hearing on ${formatPlainDate(entry.business_date)}`}
      className="animate-rise-in space-y-3 motion-reduce:animate-none"
    >
      <div className="flex items-start gap-3">
        <DateChip iso={entry.business_date} />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Last hearing</p>
          <p className="text-base font-semibold text-gray-900">{formatPlainDate(entry.business_date)}</p>
          {entry.court_name && (
            <p className="mt-0.5 flex items-start gap-1.5 text-sm text-gray-600">
              <Gavel className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />
              <span className="break-words">{entry.court_name}</span>
            </p>
          )}
        </div>
      </div>
      <BusinessText text={entry.business_text} clampLines={3} />
      <NextHearing entry={entry} />
    </article>
  );
}

function Timeline({ entries }: { entries: DailyStatusEntry[] }) {
  const [open, setOpen] = useState(false);
  if (entries.length === 0) return null;
  return (
    <div className="border-t border-gray-100 pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex min-h-[44px] w-full items-center justify-between text-sm font-medium text-gray-700"
      >
        <span>
          Earlier hearings <span className="text-gray-400">({entries.length})</span>
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cn("h-4 w-4 transition-transform motion-reduce:transition-none", open && "rotate-180")}
        />
      </button>
      {open && (
        <ol className="relative ml-5 mt-2 space-y-4 border-l border-gray-200 pl-5">
          {entries.map((entry, i) => (
            <li
              key={entry.business_date}
              style={staggerDelay(i, 45)}
              className="relative animate-fade-up motion-reduce:animate-none"
            >
              <span
                aria-hidden="true"
                className="absolute -left-[27px] top-1.5 h-3 w-3 rounded-full border-2 border-white bg-gray-400"
              />
              <p className="text-sm font-semibold text-gray-900">{formatPlainDate(entry.business_date)}</p>
              <div className="mt-1 space-y-2">
                <BusinessText text={entry.business_text} clampLines={2} />
                {entry.next_purpose && (
                  <p className="text-xs text-gray-500">
                    Then: <PurposePill purpose={entry.next_purpose} />
                    {entry.next_hearing_date && <> on {formatPlainDate(entry.next_hearing_date)}</>}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export interface DailyStatusViewProps {
  entries: DailyStatusEntry[] | undefined;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
}

/** The card body for given data; DailyStatusCard wires it to the API. */
export function DailyStatusView({ entries, isLoading, isError, onRetry }: DailyStatusViewProps) {
  let body;
  if (isLoading) {
    body = (
      <div role="status" aria-label="Loading daily status" className="flex gap-3">
        <div className="h-16 w-14 animate-pulse rounded-xl bg-gray-200 motion-reduce:animate-none" />
        <div className="flex-1 space-y-2 pt-1">
          <div className="h-3 w-1/3 animate-pulse rounded bg-gray-200 motion-reduce:animate-none" />
          <div className="h-3 w-full animate-pulse rounded bg-gray-200 motion-reduce:animate-none" />
          <div className="h-3 w-4/5 animate-pulse rounded bg-gray-200 motion-reduce:animate-none" />
        </div>
      </div>
    );
  } else if (isError) {
    body = (
      <div className="space-y-2 text-sm text-gray-700">
        <p>We couldn&apos;t load what the court recorded. Your connection may have dropped.</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex min-h-[44px] items-center gap-1.5 font-medium text-blue-700"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Try again
          </button>
        )}
      </div>
    );
  } else if (!entries || entries.length === 0) {
    body = (
      <p className="text-sm text-gray-600">
        Nothing recorded yet. After the case is refreshed from eCourts, what the court noted at each
        hearing appears here.
      </p>
    );
  } else {
    const [latest, ...earlier] = entries;
    body = (
      <div className="space-y-3">
        <LatestEntry entry={latest} />
        <Timeline entries={earlier} />
      </div>
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="px-4 pb-4 pt-3.5 sm:px-5">
        <h3 className="mb-3 text-base font-semibold text-gray-900">Daily status</h3>
        {body}
      </div>
    </Card>
  );
}

export function DailyStatusCard({ caseId }: { caseId: number }) {
  const { data, isLoading, isError, refetch } = useDailyStatus(caseId);
  return (
    <DailyStatusView
      entries={data}
      isLoading={isLoading}
      isError={isError}
      onRetry={() => void refetch()}
    />
  );
}
