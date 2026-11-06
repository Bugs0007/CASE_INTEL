"use client";

import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatClock, formatShort } from "@/lib/advocate-search-results";
import type { CourtsStatus } from "@/types";

/** The progress card of a running search: which districts, how far along, how
 * many courts need attention, and how long it has been and is expected to be.
 * The bar is green for finished courts, red for failed ones, blue for the one
 * being read; the total grows as each district's courts are listed. */
export function SearchProgress({
  title,
  courts,
  elapsedSeconds,
  matchedSoFar,
  onStop,
  stopping,
}: {
  title: string;
  courts: CourtsStatus;
  elapsedSeconds: number;
  matchedSoFar: number;
  onStop: () => void;
  stopping: boolean;
}) {
  const { counts, job } = courts;
  const total = Math.max(1, counts.total);
  const pct = (n: number) => `${(n / total) * 100}%`;
  const chip = job.cancel_requested ? "Stopping…" : job.is_retrying ? "Retrying courts" : job.status === "queued" ? "Waiting for the worker" : "Running";
  const finished = counts.done + counts.failed;

  return (
    <section aria-label="Search progress" className="shrink-0 rounded-lg border border-gray-200 bg-surface px-4 py-3">
      <div className="flex items-center gap-3">
        <h2 className="min-w-0 truncate font-serif text-[17px] font-bold text-gray-900">{title}</h2>
        <span className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-[#e5eefc] px-2 py-0.5 text-[11px] font-semibold text-[#1b4a9a]">
          <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" />
          {chip}
        </span>
        <span className="flex-1" />
        <Button variant="secondary" size="sm" onClick={onStop} disabled={stopping || job.cancel_requested}>
          Stop
        </Button>
      </div>
      <div
        role="progressbar"
        aria-label="Courts searched"
        aria-valuemin={0}
        aria-valuemax={counts.total}
        aria-valuenow={finished}
        className="mt-2 flex h-2 overflow-hidden rounded bg-gray-200"
      >
        <i className="block h-full bg-[#2f8f5b] transition-[width] duration-200 motion-reduce:transition-none" style={{ width: pct(counts.done) }} />
        <i className="block h-full bg-[#d4351c] transition-[width] duration-200 motion-reduce:transition-none" style={{ width: pct(counts.failed) }} />
        <i className="block h-full bg-[#2b6fd6] transition-[width] duration-200 motion-reduce:transition-none" style={{ width: pct(counts.running) }} />
      </div>
      <p className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-gray-600" data-testid="search-progress">
        <span>
          <b className="text-[15px] font-semibold text-gray-900">{finished}</b> of {counts.total} complexes done
        </span>
        <span>
          <b className="text-[15px] font-semibold text-gray-900">{counts.failed}</b> need attention
        </span>
        <span>
          <b className="text-[15px] font-semibold text-gray-900">{counts.running}</b> running
        </span>
        <span>
          <b className="text-[15px] font-semibold text-gray-900">{matchedSoFar}</b> cases matched so far
        </span>
        <span>
          <b className="text-[15px] font-semibold text-gray-900">{formatClock(elapsedSeconds)}</b> elapsed
        </span>
        {courts.seconds_left !== null && (
          <span>
            about <b className="text-[15px] font-semibold text-gray-900">{formatShort(courts.seconds_left)}</b> left
          </span>
        )}
      </p>
    </section>
  );
}
