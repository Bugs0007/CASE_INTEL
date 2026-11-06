"use client";

import { Loader2 } from "lucide-react";

/** The bar at the foot of the results: how many rows are ticked, how many of them
 * are already in Cases (skipped), a shortcut to tick every verified row, and the
 * button that starts the existing import. */
export function ImportBar({
  selectedCount,
  skippedCount,
  verifiedCount,
  onSelectVerified,
  onImport,
  importing,
  cap,
}: {
  selectedCount: number;
  skippedCount: number;
  verifiedCount: number;
  onSelectVerified: () => void;
  onImport: () => void;
  importing: boolean;
  cap: number;
}) {
  const over = selectedCount > cap;
  return (
    <div
      role="region"
      aria-label="Import selected cases"
      className="flex shrink-0 items-center gap-3.5 rounded-[10px] bg-primary px-3.5 py-2.5 text-page shadow-card"
    >
      <b className="font-semibold">{selectedCount} selected</b>
      {skippedCount > 0 && <span className="text-xs text-[#b8c4d6]">{skippedCount} already in Cases is skipped</span>}
      {over && <span className="text-xs text-[#f3c9c1]">Only the first {cap} are added at a time.</span>}
      <span className="flex-1" />
      <button
        type="button"
        onClick={onSelectVerified}
        disabled={verifiedCount === 0}
        className="text-[13px] text-[#b8c4d6] underline-offset-2 hover:text-page hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-page disabled:opacity-50"
      >
        Select all verified ({verifiedCount})
      </button>
      <button
        type="button"
        onClick={onImport}
        disabled={selectedCount === 0 || importing}
        className="inline-flex items-center gap-2 rounded-md bg-[#f2f0ea] px-3.5 py-1.5 text-[13px] font-bold text-[#17202e] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-page disabled:opacity-50"
      >
        {importing && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
        {selectedCount === 1 ? "Import 1 case" : `Import ${selectedCount} cases`}
      </button>
    </div>
  );
}
