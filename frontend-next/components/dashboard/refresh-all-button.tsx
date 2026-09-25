"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, RefreshCw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { showToast } from "@/components/ui/toaster";
import {
  isRunActive,
  useCancelRefreshAll,
  useLatestRefreshRun,
  useRefreshRun,
  useStartRefreshAll,
} from "@/hooks/use-clients";
import { APIError, apiErrorDetail } from "@/lib/api/client";
import { formatRelativeTime } from "@/lib/utils";
import type { RefreshRun } from "@/types";

function summary(run: RefreshRun): string {
  const r = run.results;
  const parts = [
    `${r.refreshed} refreshed`,
    r.rate_limited ? `${r.rate_limited} skipped (checked in the last hour)` : "",
    r.failed ? `${r.failed} failed` : "",
    r.new_hearing_dates ? `${r.new_hearing_dates} new hearing date${r.new_hearing_dates === 1 ? "" : "s"}` : "",
    r.drafts_created ? `${r.drafts_created} client update${r.drafts_created === 1 ? "" : "s"} drafted` : "",
  ].filter(Boolean);
  return parts.join(" · ");
}

/** "Last run 9 min ago · 24 checked · 5 updated · 0 errors" -- what the
 * last finished run did, so the button isn't a leap of faith. */
export function lastRunLine(run: RefreshRun): string {
  const r = run.results;
  const when = run.finished_at ? formatRelativeTime(run.finished_at) : formatRelativeTime(run.created_at);
  const stopped =
    run.status === "cancelled" ? " (cancelled)" : run.status === "failed" || run.aborted_reason ? " (stopped early)" : "";
  return [
    `Last run ${when}${stopped}`,
    `${run.done} checked`,
    `${r.updated ?? 0} updated`,
    `${r.failed} error${r.failed === 1 ? "" : "s"}`,
  ].join(" · ");
}

/** "Refresh all tracked cases" -- fetches every open tracked case from
 * eCourts, one at a time, in the background worker.
 *
 * Stand-in for a nightly refresh until the server can afford one. Cases
 * fetched in the last hour are skipped (the per-case limit still holds),
 * and only one refresh can run on the server at a time. Picks a running
 * refresh back up after a page reload. */
export function RefreshAllButton() {
  const [jobId, setJobId] = useState<number | null>(null);
  const latest = useLatestRefreshRun();
  const run = useRefreshRun(jobId);
  const start = useStartRefreshAll();
  const cancel = useCancelRefreshAll();
  const announced = useRef<number | null>(null);

  // Resume a run that was already going when the page loaded.
  useEffect(() => {
    const l = latest.data;
    if (jobId === null && l && l.job_id !== null && isRunActive(l as RefreshRun)) {
      setJobId(l.job_id);
      announced.current = null;
    }
  }, [latest.data, jobId]);

  const current = run.data;
  const active = isRunActive(current);

  // One toast when a run this page was watching finishes.
  useEffect(() => {
    if (!current || active || jobId === null || announced.current === current.job_id) return;
    announced.current = current.job_id;
    if (current.status === "cancelled") {
      showToast.info("Refresh cancelled", summary(current));
    } else if (current.aborted_reason) {
      showToast.warning("Refresh stopped early", `${current.aborted_reason} ${summary(current)}`);
    } else if (current.status === "failed") {
      showToast.error("Refresh failed", current.error || "Please try again later.");
    } else {
      showToast.success("Tracked cases refreshed", summary(current));
    }
  }, [current, active, jobId]);

  async function handleStart() {
    try {
      const started = await start.mutateAsync();
      announced.current = null;
      setJobId(started.job_id);
    } catch (error) {
      const body = error instanceof APIError ? (error.data as { code?: string; job_id?: number }) : null;
      if (body?.code === "already_running" && body.job_id) {
        setJobId(body.job_id); // your own run -- show its progress
        return;
      }
      showToast.error("Could not start the refresh", apiErrorDetail(error, "Please try again."));
    }
  }

  async function handleCancel() {
    if (jobId === null) return;
    try {
      await cancel.mutateAsync(jobId);
    } catch (error) {
      showToast.error("Could not cancel", apiErrorDetail(error, "Please try again."));
    }
  }

  const pct = current && current.total ? Math.round((current.done / current.total) * 100) : 0;
  // The run this page watched, else the latest from the server.
  const latestRun = latest.data && latest.data.job_id !== null ? (latest.data as RefreshRun) : null;
  const lastRun = [current, latestRun].find((r): r is RefreshRun => !!r && !isRunActive(r)) ?? null;

  return (
    <div className="mb-5 flex flex-wrap items-center gap-3">
      {active && current ? (
        <div className="flex flex-1 min-w-[240px] items-center gap-3">
          <Loader2 className="h-4 w-4 animate-spin text-gray-500 flex-shrink-0" />
          <div className="flex-1">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>
                {current.status === "queued" ? "Waiting for the worker…" : "Refreshing tracked cases…"}
              </span>
              <span>
                {current.done} / {current.total}
              </span>
            </div>
            <div
              className="h-1.5 rounded-full bg-gray-100 overflow-hidden"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={current.total}
              aria-valuenow={current.done}
              aria-label="Refresh progress"
            >
              <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={handleCancel} disabled={cancel.isPending}>
            <X className="h-4 w-4" />
            Cancel
          </Button>
        </div>
      ) : (
        <>
          <Button variant="secondary" size="sm" onClick={handleStart} disabled={start.isPending}>
            {start.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Refresh all tracked cases
          </Button>
          <span className="text-xs text-gray-500">
            Checks eCourts for every open tracked case, one at a time. Cases checked in the last hour are skipped.
          </span>
          {lastRun && (
            <span className="basis-full text-xs text-gray-600" data-testid="refresh-last-run">
              {lastRunLine(lastRun)}
            </span>
          )}
        </>
      )}
    </div>
  );
}
