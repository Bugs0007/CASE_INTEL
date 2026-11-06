"use client";

import { useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { AlertTriangle, ChevronDown, Loader2, MapPin, RotateCcw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { caseTrackingApi } from "@/lib/api/case-tracking";
import { courtStructureKeys, useCourtStructure } from "@/hooks/use-case-tracking";
import { describeEstimate, estimateSeconds } from "@/lib/advocate-search-results";
import { cn } from "@/lib/utils";
import { Eyebrow, Notice, Panel, Seg } from "./ui";

const label = (value: unknown): string => (typeof value === "string" ? value : ((value as { label?: string })?.label ?? ""));

export type StatusFilter = "Pending" | "Disposed" | "Both";

/** Where to search: the state, the districts (a district's courts are read as the
 * search runs), the case status, and the Search button. The states and districts
 * come from the court portal; if that fails the panel says so and offers Retry,
 * never an empty list. */
export function DistrictPicker({
  stateCode,
  onStateChange,
  distCodes,
  onDistCodesChange,
  status,
  onStatusChange,
  searchBy,
  onSearchByChange,
  hasBarCode,
  queryCount,
  secondsPerCall,
  canSearch,
  isSearching,
  error,
  onSearch,
}: {
  stateCode: string;
  onStateChange: (code: string) => void;
  distCodes: string[];
  onDistCodesChange: (codes: string[]) => void;
  status: StatusFilter;
  onStatusChange: (status: StatusFilter) => void;
  searchBy: "names" | "bar_code";
  onSearchByChange: (by: "names" | "bar_code") => void;
  hasBarCode: boolean;
  queryCount: number;
  secondsPerCall: number;
  canSearch: boolean;
  isSearching: boolean;
  error: string;
  onSearch: () => void;
}) {
  const [filter, setFilter] = useState("");
  const [changingState, setChangingState] = useState(false);
  const states = useCourtStructure({ court_type: "district" });
  const districts = useCourtStructure(stateCode ? { court_type: "district", state_code: stateCode } : null);

  const stateName = label(states.data?.options?.[stateCode]);
  const all = useMemo(() => Object.entries(districts.data?.options ?? {}).map(([code, v]) => ({ code, name: label(v) })), [districts.data]);
  const shown = all.filter((d) => d.name.toLowerCase().includes(filter.trim().toLowerCase()));

  // How many courts the ticked districts hold, so the estimate is a real count.
  // Only the ticked ones are asked (each is a portal lookup the server caches).
  const complexQueries = useQueries({
    queries: distCodes.map((code) => ({
      queryKey: courtStructureKeys.level({ court_type: "district", state_code: stateCode, dist_code: code }),
      queryFn: () => caseTrackingApi.courtStructure({ court_type: "district", state_code: stateCode, dist_code: code }),
      staleTime: 60 * 60 * 1000,
      enabled: !!stateCode,
    })),
  });
  const complexCount = (code: string) => {
    const q = complexQueries[distCodes.indexOf(code)];
    return q?.data ? Object.keys(q.data.options ?? {}).length : null;
  };
  const totalCourts = complexQueries.reduce((n, q) => n + (q.data ? Object.keys(q.data.options ?? {}).length : 0), 0);
  const stillCounting = complexQueries.some((q) => q.isLoading);
  const calls = searchBy === "bar_code" ? 1 : Math.max(1, queryCount);
  const seconds = estimateSeconds(totalCourts, calls, secondsPerCall);

  const toggle = (code: string) =>
    onDistCodesChange(distCodes.includes(code) ? distCodes.filter((c) => c !== code) : [...distCodes, code]);

  const failure = states.isError ? { what: "the states", retry: () => states.refetch() } : districts.isError && stateCode ? { what: "the districts", retry: () => districts.refetch() } : null;

  return (
    <Panel
      title="Where to search"
      icon={<MapPin className="h-[17px] w-[17px]" />}
      sub={stateName}
      label="Where to search"
      className="h-full"
      action={
        <Button variant="secondary" size="sm" onClick={() => setChangingState((v) => !v)} aria-expanded={changingState}>
          Change state <ChevronDown className="h-3 w-3" />
        </Button>
      }
    >
      {(changingState || !stateCode) && (
        <Select
          aria-label="State"
          value={stateCode}
          disabled={states.isLoading || states.isError}
          onChange={(e) => {
            onStateChange(e.target.value);
            onDistCodesChange([]);
            setChangingState(false);
          }}
        >
          <option value="">{states.isLoading ? "Loading states…" : "Select a state"}</option>
          {Object.entries(states.data?.options ?? {}).map(([code, v]) => (
            <option key={code} value={code}>
              {label(v)}
            </option>
          ))}
        </Select>
      )}

      {failure ? (
        <div role="alert" className="flex flex-col items-start gap-2 rounded-md border border-status-alert bg-status-alert-soft p-4 text-sm text-status-alert">
          <p className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              The court portal didn&apos;t send {failure.what}. It sometimes drops the first connection; this is not an empty list. Try again.
            </span>
          </p>
          <Button variant="secondary" size="sm" onClick={failure.retry}>
            <RotateCcw className="h-3.5 w-3.5" />
            Retry
          </Button>
        </div>
      ) : (
        <>
          <div className="flex shrink-0 flex-wrap items-end gap-x-4 gap-y-2">
            <div>
              <Eyebrow>Status</Eyebrow>
              <Seg
                label="Case status"
                value={status}
                onChange={onStatusChange}
                options={[
                  { value: "Pending", label: "Pending" },
                  { value: "Disposed", label: "Disposed" },
                  { value: "Both", label: "Both" },
                ]}
              />
            </div>
            {hasBarCode && (
              <div>
                <Eyebrow>Search by</Eyebrow>
                <Seg
                  label="Search by"
                  value={searchBy}
                  onChange={onSearchByChange}
                  options={[
                    { value: "bar_code", label: "Bar number" },
                    { value: "names", label: "Names" },
                  ]}
                />
              </div>
            )}
            <div className="min-w-[140px] flex-1">
              <Eyebrow>Search</Eyebrow>
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter districts"
                aria-label="Filter districts"
                className="h-8 w-full rounded-md border border-gray-300 bg-surface px-3 text-[13px] outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <ul
            aria-label="Districts"
            className="min-h-[120px] flex-1 divide-y divide-gray-100 overflow-y-auto rounded-md border border-gray-200"
          >
            {districts.isLoading && (
              <li className="flex items-center gap-2 px-3 py-3 text-sm text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                Loading districts…
              </li>
            )}
            {!stateCode && <li className="px-3 py-3 text-sm text-gray-500">Pick a state to see its districts.</li>}
            {shown.map((d) => (
              <li key={d.code}>
                <label className="flex h-[33px] cursor-pointer items-center gap-2.5 px-3 text-[13px] hover:bg-gray-50">
                  <input type="checkbox" checked={distCodes.includes(d.code)} onChange={() => toggle(d.code)} className="h-4 w-4 accent-primary" />
                  <span className="min-w-0 flex-1 truncate">{d.name}</span>
                  {distCodes.includes(d.code) && (
                    <span className="font-sans text-xs text-gray-500">
                      {complexCount(d.code) === null ? "…" : `${complexCount(d.code)} complexes`}
                    </span>
                  )}
                </label>
              </li>
            ))}
            {stateCode && !districts.isLoading && shown.length === 0 && all.length > 0 && (
              <li className="px-3 py-3 text-sm text-gray-500">No district matches that filter.</li>
            )}
          </ul>

          <div className="flex shrink-0 items-center gap-2.5 text-[13px]">
            <span>
              <b className="font-semibold">{distCodes.length === 1 ? "1 district" : `${distCodes.length} districts`}</b>
              {" · "}
              {stillCounting ? "counting courts…" : `${totalCourts} court complex${totalCourts === 1 ? "" : "es"}`}
            </span>
            <span className="flex-1" />
            <Button variant="secondary" size="sm" disabled={all.length === 0} onClick={() => onDistCodesChange(all.map((d) => d.code))}>
              Select all
            </Button>
            <Button variant="secondary" size="sm" disabled={distCodes.length === 0} onClick={() => onDistCodesChange([])}>
              Clear
            </Button>
          </div>

          <Notice className="shrink-0 bg-[#f6f8fb] text-[13px] text-gray-800">
            <span>
              Estimated time: <b className="font-semibold">{totalCourts === 0 ? "pick a district" : describeEstimate(seconds)}</b>
              {queryCount > 1 && searchBy === "names" ? ` (${queryCount} searches on every court)` : ""}. You can leave this page; the search keeps
              running and the courts list shows exactly where it stands.
            </span>
          </Notice>
          {error && (
            <Notice tone="alert" className="shrink-0">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{error}</span>
            </Notice>
          )}
          <Button
            type="button"
            size="lg"
            disabled={!canSearch || isSearching || distCodes.length === 0}
            onClick={onSearch}
            className={cn("h-10 w-full shrink-0")}
          >
            {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
            {distCodes.length === 0 ? "Pick a district to search" : `Search ${distCodes.length === 1 ? "1 district" : `${distCodes.length} districts`}`}
          </Button>
        </>
      )}
    </Panel>
  );
}
