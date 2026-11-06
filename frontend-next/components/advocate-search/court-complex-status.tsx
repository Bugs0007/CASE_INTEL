"use client";

import { AlertTriangle, ExternalLink, Loader2, RotateCcw, Scale } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { CourtRun, CourtsStatus } from "@/types";
import { Panel } from "./ui";

const DOT: Record<CourtRun["status"], string> = {
  done: "bg-[#2f8f5b]",
  running: "bg-[#2b6fd6] shadow-[0_0_0_3px_#2b6fd633]",
  pending: "bg-[#cfcabd]",
  failed: "bg-[#d4351c]",
};

function FailedRow({ run, canRetry, onRetry }: { run: CourtRun; canRetry: boolean; onRetry: (id: number) => void }) {
  return (
    <li className="flex items-start gap-2.5 border-t border-gray-100 bg-status-alert-soft px-3.5 py-2 text-[13px]">
      <i aria-hidden className={cn("mt-1.5 h-[9px] w-[9px] shrink-0 rounded-full", DOT.failed)} />
      <div className="min-w-0 flex-1">
        <b className="font-semibold">
          {run.complex_name}
          {run.dist_name && !run.complex_name.includes(run.dist_name) ? `, ${run.dist_name}` : ""}
        </b>
        <div className="text-xs text-status-alert">
          {run.reason}
          {run.finished_at && <> Last tried {formatRelativeTime(run.finished_at)}.</>}
        </div>
      </div>
      {canRetry && (
        <Button size="sm" onClick={() => onRetry(run.id)} aria-label={`Retry ${run.complex_name}`}>
          Retry
        </Button>
      )}
    </li>
  );
}

/** Every court complex of the search with its own live status, grouped by
 * district. Failed courts are pinned on top with the reason in plain words and a
 * Retry; they are searched again alone and merged into the same results. */
export function CourtComplexStatus({
  courts,
  onRetryOne,
  onRetryFailed,
  retrying,
}: {
  courts: CourtsStatus;
  onRetryOne: (id: number) => void;
  onRetryFailed: () => void;
  retrying: boolean;
}) {
  const failed = courts.needs_attention;
  const canRetry = courts.job.can_retry && !retrying;
  const live = courts.job.status === "queued" || courts.job.status === "running" || courts.job.is_retrying;

  return (
    <Panel
      title="Court complexes"
      icon={<Scale className="h-[17px] w-[17px]" />}
      sub={live ? "Live" : undefined}
      label="Court complexes"
      className="h-full"
      bodyClassName="p-0 gap-0 overflow-y-auto"
      action={
        failed.length > 0 && courts.job.can_retry ? (
          <Button variant="secondary" size="sm" onClick={onRetryFailed} disabled={retrying}>
            {retrying ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCcw className="h-3 w-3" />}
            Retry failed ({failed.length})
          </Button>
        ) : undefined
      }
    >
      {courts.counts.total === 0 && (
        <p className="flex items-center gap-2 px-4 py-3 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          Waiting for the first district&apos;s courts to be listed…
        </p>
      )}

      {failed.length > 0 && (
        <div data-testid="needs-attention">
          <div className="flex items-center gap-2 bg-status-alert-soft px-3.5 py-2 text-[13px] font-semibold text-status-alert">
            <AlertTriangle className="h-3.5 w-3.5" />
            Needs attention
            <span className="ml-auto font-mono text-[11px] font-medium">
              {failed.length} failed{courts.job.can_retry ? " · you can search these again" : ""}
            </span>
          </div>
          <ul>
            {failed.map((run) => (
              <FailedRow key={run.id} run={run} canRetry={canRetry} onRetry={onRetryOne} />
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 px-3.5 py-2">
            {courts.job.can_retry && (
              <Button size="sm" onClick={onRetryFailed} disabled={retrying}>
                Search only these {failed.length} again
              </Button>
            )}
            <span className="text-xs text-gray-500">Or open the court site yourself and search there.</span>
            <a
              href={courts.court_site_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-xs font-semibold text-primary underline"
            >
              Open the court site <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      )}

      {courts.groups.map((group) => (
        <div key={group.dist_code}>
          <div className="flex items-center gap-2 border-t border-gray-100 bg-gray-50 px-3.5 py-2 text-[13px] font-semibold">
            {group.name}
            <span className="ml-auto font-mono text-[11px] font-medium text-gray-500">
              {group.running > 0 ? `${group.running} of ${group.total} running` : `${group.done} of ${group.total} done`}
              {group.failed > 0 ? ` · ${group.failed} failed` : ""}
            </span>
          </div>
          <ul>
            {group.runs
              .filter((r) => r.status !== "failed")
              .map((run) => (
                <li key={run.id} className="flex h-[34px] items-center gap-2.5 border-t border-gray-100 px-3.5 text-[13px]">
                  <i aria-hidden className={cn("h-[9px] w-[9px] shrink-0 rounded-full", DOT[run.status])} />
                  <span className="min-w-0 flex-1 truncate">{run.complex_name}</span>
                  <span className="whitespace-nowrap text-xs text-gray-500">
                    {run.status === "done"
                      ? `${run.matched_count} matched${run.seconds !== null ? ` · ${run.seconds} s` : ""}`
                      : run.reason}
                  </span>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </Panel>
  );
}
