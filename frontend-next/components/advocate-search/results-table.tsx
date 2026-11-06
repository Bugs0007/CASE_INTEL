"use client";

import { Ban, UserCheck } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AdvocateResultRow } from "@/types";
import { MatchChip } from "./ui";

/** Which of a row's listed advocates "Not me" / "That's me" is about: the longest
 * one, which is the name, not a designation such as "APP". */
export function pickListedName(row: AdvocateResultRow): string {
  const parts = row.listed_advocates?.length ? row.listed_advocates : row.listed_advocate_name ? [row.listed_advocate_name] : [];
  return [...parts].sort((a, b) => b.length - a.length)[0] ?? "";
}

const th = "border-b border-gray-200 bg-gray-50 px-2.5 py-2 text-left font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-gray-500 whitespace-nowrap";

/** The finished search's rows. Every row says how it relates to the advocate;
 * a row can be marked Not me or That's me without searching again. */
export function ResultsTable({
  rows,
  selected,
  inCases,
  onToggle,
  onToggleAll,
  onNameAction,
  showStatus,
}: {
  rows: AdvocateResultRow[];
  selected: Set<string>;
  inCases: Set<string>;
  onToggle: (cnr: string) => void;
  onToggleAll: () => void;
  onNameAction: (row: AdvocateResultRow, action: "exclude" | "add") => void;
  showStatus: boolean;
}) {
  const selectable = rows.filter((r) => !inCases.has(r.cnr_number));
  const allOn = selectable.length > 0 && selectable.every((r) => selected.has(r.cnr_number));

  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-gray-200 bg-surface" data-testid="results-scroll">
      <table className="w-full border-collapse text-[13px]">
        <thead className="sticky top-0 z-10">
          <tr>
            <th className={cn(th, "w-9")}>
              <input type="checkbox" aria-label="Select all shown" className="h-4 w-4 accent-primary" checked={allOn} onChange={onToggleAll} />
            </th>
            <th className={th}>Case no.</th>
            <th className={th}>Parties</th>
            <th className={th}>Advocate as listed</th>
            <th className={th}>Court</th>
            {showStatus && <th className={th}>Status</th>}
            <th className={th}>Match</th>
            <th className={cn(th, "w-[170px]")}>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const status = r.match_status ?? "check";
            const imported = inCases.has(r.cnr_number);
            const listed = r.listed_advocates?.join(" · ") || r.listed_advocate_name || "";
            const canAct = r.match_source !== "bar_code" && !!pickListedName(r);
            return (
              <tr
                key={r.cnr_number}
                className={cn(
                  "group border-b border-gray-100 align-top",
                  selected.has(r.cnr_number) && "bg-[#f3f7fd]",
                  (imported || status === "excluded") && "text-gray-500",
                )}
              >
                <td className="px-2.5 py-2">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-primary"
                    aria-label={`Select ${r.case_number}`}
                    disabled={imported}
                    checked={selected.has(r.cnr_number)}
                    onChange={() => onToggle(r.cnr_number)}
                  />
                </td>
                <td className="whitespace-nowrap px-2.5 py-2 font-mono font-bold">{r.case_number}</td>
                <td className="px-2.5 py-2">
                  {r.petitioner || "—"} vs. {r.respondent || "—"}
                </td>
                <td className="px-2.5 py-2">{listed || <span className="text-gray-400">not listed</span>}</td>
                <td className="px-2.5 py-2">{r.complex_name || r.court_name || "—"}</td>
                {showStatus && <td className="px-2.5 py-2">{r.status || "—"}</td>}
                <td className="px-2.5 py-2">
                  <MatchChip status={status} label={r.match_label} />
                </td>
                <td className="whitespace-nowrap px-2.5 py-1.5 text-right">
                  {imported ? (
                    <span className="text-xs font-semibold text-status-ok">Already in Cases</span>
                  ) : (
                    canAct && (
                      <span
                        className={cn(
                          "inline-flex gap-1.5",
                          status === "matched" && "opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100 motion-reduce:transition-none",
                        )}
                      >
                        {status !== "excluded" && (
                          <button
                            type="button"
                            onClick={() => onNameAction(r, "exclude")}
                            aria-label={`Not me: ${pickListedName(r)}`}
                            className="inline-flex h-[26px] items-center gap-1 rounded-md border border-gray-300 bg-surface px-2.5 text-xs font-semibold hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                          >
                            <Ban className="h-3 w-3" />
                            Not me
                          </button>
                        )}
                        {status !== "matched" && (
                          <button
                            type="button"
                            onClick={() => onNameAction(r, "add")}
                            aria-label={`That's me: ${pickListedName(r)}`}
                            className="inline-flex h-[26px] items-center gap-1 rounded-md border border-gray-300 bg-surface px-2.5 text-xs font-semibold hover:bg-gray-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                          >
                            <UserCheck className="h-3 w-3" />
                            That&apos;s me
                          </button>
                        )}
                      </span>
                    )
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {rows.length === 0 && <p className="px-4 py-6 text-center text-sm text-gray-500">No rows match these filters.</p>}
    </div>
  );
}
