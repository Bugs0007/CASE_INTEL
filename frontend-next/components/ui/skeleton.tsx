import { cn } from "@/lib/utils";

/** A grey placeholder block. Pulses on desktop; on a phone `.ci-skeleton`
 * (globals.css) swaps the pulse for a light shimmer sweeping across it. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("ci-skeleton animate-pulse rounded bg-gray-200/60", className)} />;
}
