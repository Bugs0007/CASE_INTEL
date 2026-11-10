import type { AdvocateSearchJobResult } from "@/types";

/** "42s", "4m 12s", "1h 05m". Never negative. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours}h ${String(minutes).padStart(2, "0")}m`;
  if (minutes > 0) return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
  return `${seconds}s`;
}

/** After this long still queued, say the worker is probably busy. */
export const LONG_WAIT_MS = 60_000;

export interface SearchProgressText {
  /** Set while the search is still waiting for the worker. */
  waiting: string | null;
  /** "12 of 40 court complexes searched", once a district has been listed. */
  counts: string | null;
  /** The district being searched right now. */
  district: string | null;
  /** "Elapsed 4m 12s", from when the worker started it. */
  elapsed: string | null;
}

type ProgressJob = Pick<
  AdvocateSearchJobResult,
  | "status"
  | "created_at"
  | "started_at"
  | "progress_current"
  | "progress_total"
  | "complexes_done"
  | "complexes_total_known"
  | "current_district"
>;

const NOTHING: SearchProgressText = { waiting: null, counts: null, district: null, elapsed: null };

/** What the search page says about a search that has not finished: honest
 * about what is known. A district's complex count is known once it is listed,
 * so "N of M" can have more districts still to come, and says so. */
export function describeSearchProgress(job: ProgressJob, nowMs: number): SearchProgressText {
  if (job.status === "queued") {
    const waited = nowMs - new Date(job.created_at).getTime();
    let waiting =
      "Waiting for the background worker to start this search. If other jobs (order checks, " +
      "refreshes, uploads, another search) are running, it starts when the worker is free.";
    if (Number.isFinite(waited) && waited >= LONG_WAIT_MS) {
      waiting += ` Still waiting after ${formatElapsed(waited)}. The worker may be busy with another job.`;
    }
    return { ...NOTHING, waiting };
  }
  if (job.status !== "running") return NOTHING;

  const known = job.complexes_total_known ?? 0;
  const done = job.complexes_done ?? 0;
  let counts: string;
  if (known > 0) {
    counts = `${done} of ${known} court complexes searched`;
    const unlisted = Math.max(0, (job.progress_total || 0) - (job.progress_current || 0) - (job.current_district ? 1 : 0));
    if (unlisted > 0) counts += ` · ${unlisted} more district${unlisted === 1 ? "" : "s"} still to be listed`;
  } else {
    counts = "Listing the court complexes…";
  }

  const started = job.started_at ? new Date(job.started_at).getTime() : NaN;
  return {
    waiting: null,
    counts,
    district: job.current_district ? `Now searching ${job.current_district}` : null,
    elapsed: Number.isFinite(started) ? `Elapsed ${formatElapsed(nowMs - started)}` : null,
  };
}
