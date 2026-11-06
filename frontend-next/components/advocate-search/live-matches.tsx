"use client";

import { Ban, Zap } from "lucide-react";
import type { AdvocateResultRow } from "@/types";
import { MatchChip, Panel } from "./ui";

/** "Found so far": the rows that look like the advocate's, as courts finish. Rows
 * the profile hides (Not me, other names) are counted underneath, not listed. */
export function LiveMatches({ rows, hiddenCount }: { rows: AdvocateResultRow[]; hiddenCount: number }) {
  return (
    <Panel
      title="Found so far"
      icon={<Zap className="h-[17px] w-[17px]" />}
      sub="Matches appear as soon as a court finishes"
      label="Found so far"
      className="h-full"
      bodyClassName="p-0 gap-0"
    >
      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <p className="px-4 py-4 text-sm text-gray-500">Nothing yet. The first court is still being read.</p>
        ) : (
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="sticky top-0 bg-gray-50 text-left font-mono text-[10.5px] uppercase tracking-[0.08em] text-gray-500">
                <th className="border-b border-gray-200 px-3 py-2 font-medium">Case</th>
                <th className="border-b border-gray-200 px-3 py-2 font-medium">Parties</th>
                <th className="border-b border-gray-200 px-3 py-2 font-medium">Match</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.cnr_number} className="border-b border-gray-100">
                  <td className="whitespace-nowrap px-3 py-2 font-mono font-bold">{r.case_number}</td>
                  <td className="px-3 py-2">
                    {r.petitioner || "—"} vs. {r.respondent || "—"}
                  </td>
                  <td className="px-3 py-2">
                    <MatchChip status={r.match_status ?? "check"} label={r.match_status === "matched" ? r.listed_advocate_name || r.match_label : r.match_status === "check" ? "Check" : r.match_label} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {hiddenCount > 0 && (
        <p className="flex shrink-0 items-center gap-2 border-t border-gray-200 bg-gray-50 px-3.5 py-2 text-[13px] font-semibold">
          <Ban className="h-3.5 w-3.5" />
          {hiddenCount} hidden because they matched your Not me list
        </p>
      )}
    </Panel>
  );
}
