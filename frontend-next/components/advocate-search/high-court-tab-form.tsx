"use client";

import { AlertTriangle, Gavel, Loader2, RotateCcw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { describeEstimate, estimateSeconds } from "@/lib/advocate-search-results";
import { cn } from "@/lib/utils";
import type { AdvocateSearchProfile, HighCourtBench, HighCourtInfo } from "@/types";
import { Eyebrow, Notice, Panel, Seg } from "./ui";
import type { StatusFilter } from "./district-picker";

const YEARS = Array.from({ length: new Date().getFullYear() - 1999 }, (_, i) => new Date().getFullYear() - i);

/** The High Court search form: bench checklist, status, bar number or names, the
 * year range (a filter on the result, never a new search), the estimate and the
 * Search button. */
export function HighCourtForm({
  court,
  benches,
  benchesLoading,
  benchesError,
  onRetryBenches,
  chosenBenches,
  onChosenBenches,
  status,
  onStatusChange,
  searchBy,
  onSearchByChange,
  profile,
  yearFrom,
  yearTo,
  onYearChange,
  secondsPerCall,
  isSearching,
  error,
  onSearch,
  coverage,
}: {
  court: HighCourtInfo | null;
  benches: HighCourtBench[];
  benchesLoading: boolean;
  benchesError: boolean;
  onRetryBenches: () => void;
  chosenBenches: string[];
  onChosenBenches: (codes: string[]) => void;
  status: StatusFilter;
  onStatusChange: (s: StatusFilter) => void;
  searchBy: "names" | "bar_code";
  onSearchByChange: (by: "names" | "bar_code") => void;
  profile: AdvocateSearchProfile;
  yearFrom: number | null;
  yearTo: number | null;
  onYearChange: (from: number | null, to: number | null) => void;
  secondsPerCall: number;
  isSearching: boolean;
  error: string;
  onSearch: () => void;
  /** The states and territories this High Court serves, when known. */
  coverage?: string;
}) {
  if (!court) {
    return (
      <Panel title="Search a High Court" icon={<Gavel className="h-[17px] w-[17px]" />} label="Search a High Court" className="h-full">
        <p className="text-sm text-gray-600">Choose a High Court on the left to set up the search.</p>
      </Panel>
    );
  }

  const barCode = profile.bar_codes[0] ?? "";
  const calls = searchBy === "bar_code" ? 1 : Math.max(1, profile.query_count);
  const requests = chosenBenches.length * calls;
  const toggle = (code: string) =>
    onChosenBenches(chosenBenches.includes(code) ? chosenBenches.filter((c) => c !== code) : [...chosenBenches, code]);
  const canSearch = chosenBenches.length > 0 && (searchBy === "bar_code" ? !!barCode : profile.query_count > 0);

  return (
    <Panel
      title={`Search ${court.name}`}
      icon={<Gavel className="h-[17px] w-[17px]" />}
      label={`Search ${court.name}`}
      className="h-full"
      bodyClassName="gap-3 overflow-hidden"
    >
      {/* The fields scroll; the estimate and the Search button stay in view. */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
      {coverage && (
        <Notice>
          <span>
            This High Court covers <b className="font-semibold">{coverage}</b>.
          </span>
        </Notice>
      )}

      <div className="flex flex-wrap items-start gap-x-5 gap-y-3">
        <div className="min-w-[220px] flex-1">
          <Eyebrow>{benches.length > 1 ? "Benches to search (one request each)" : "Court"}</Eyebrow>
          {benchesError ? (
            <div role="alert" className="flex items-center gap-2 rounded-md border border-status-alert bg-status-alert-soft px-3 py-2 text-xs text-status-alert">
              <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
              The portal did not list this court&apos;s benches.
              <Button variant="secondary" size="sm" onClick={onRetryBenches}>
                <RotateCcw className="h-3 w-3" />
                Retry
              </Button>
            </div>
          ) : benchesLoading ? (
            <p className="flex items-center gap-2 text-xs text-gray-500">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Asking the portal for the benches…
            </p>
          ) : (
            <ul aria-label="Benches" className="divide-y divide-gray-100 overflow-hidden rounded-md border border-gray-200">
              {benches.map((b) => (
                <li key={b.code}>
                  <label className="flex h-[31px] cursor-pointer items-center gap-2.5 px-3 text-[13px] hover:bg-gray-50">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-primary"
                      checked={chosenBenches.includes(b.code)}
                      onChange={() => toggle(b.code)}
                    />
                    <span className="truncate">{b.name.replace(/,/g, ", ")}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>
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
      </div>

      <div>
        <Eyebrow>Search by</Eyebrow>
        <div role="radiogroup" aria-label="Search by" className="flex flex-col gap-2">
          {(
            [
              {
                value: "bar_code" as const,
                title: "Bar enrolment number",
                text: barCode ? `${barCode} · exact match, one request per bench, no other advocates` : "Add a bar number to your profile to use this",
                disabled: !barCode,
              },
              {
                value: "names" as const,
                title: "Names from my profile",
                text: `${profile.queries.join(", ") || "no searchable name yet"} · filtered to your ${profile.name_forms.length} name forms and your Not me list`,
                disabled: profile.query_count === 0,
              },
            ] as const
          ).map((o) => (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={searchBy === o.value}
              disabled={o.disabled}
              onClick={() => onSearchByChange(o.value)}
              className={cn(
                "flex gap-2.5 rounded-lg border-[1.5px] px-3 py-2.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50",
                searchBy === o.value ? "border-primary bg-[#f6f8fb]" : "border-gray-200 hover:bg-gray-50",
              )}
            >
              <i
                aria-hidden
                className={cn(
                  "mt-0.5 h-4 w-4 shrink-0 rounded-full border-2",
                  searchBy === o.value ? "border-primary bg-primary shadow-[inset_0_0_0_3px_var(--ci-surface)]" : "border-gray-400",
                )}
              />
              <span className="min-w-0">
                <b className="block text-sm">{o.title}</b>
                <span className="block text-[12.5px] text-gray-600">{o.text}</span>
              </span>
            </button>
          ))}
        </div>
        {searchBy === "names" && (
          <Notice tone="warn" className="mt-2">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              A High Court result does not list the advocate on each row, so a name search cannot tell your cases from another advocate&apos;s:
              every row will say Check name. A bar number search is exact.
            </span>
          </Notice>
        )}
      </div>

      <div>
        <Eyebrow>Filing year (result filter)</Eyebrow>
        <div className="flex items-center gap-2">
          {(["from", "to"] as const).map((which, i) => (
            <span key={which} className="flex flex-1 items-center gap-2">
              {i === 1 && <span className="text-gray-500">to</span>}
              <select
                aria-label={`Year ${which}`}
                value={(which === "from" ? yearFrom : yearTo) ?? ""}
                onChange={(e) => {
                  const v = e.target.value ? Number(e.target.value) : null;
                  onYearChange(which === "from" ? v : yearFrom, which === "to" ? v : yearTo);
                }}
                className="h-9 w-full rounded-md border border-gray-300 bg-surface px-2 text-sm"
              >
                <option value="">Any year</option>
                {YEARS.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </span>
          ))}
        </div>
        <p className="mt-1 text-xs text-gray-500">
          The High Court portal returns the whole book in one go, so we fetch it once and cut it to your year range here. Changing the range
          later does not search again.
        </p>
      </div>

      </div>
      <Notice className="shrink-0 bg-[#f6f8fb] text-[13px] text-gray-800">
        <span>
          {requests === 0 ? "Pick at least one bench." : `${requests} request${requests === 1 ? "" : "s"}, one per ${calls > 1 ? "name per bench" : "bench"}. `}
          {requests > 0 && (
            <>
              Usually <b className="font-semibold">{describeEstimate(estimateSeconds(1, requests, secondsPerCall))}</b>.
            </>
          )}
        </span>
      </Notice>
      {error && (
        <Notice tone="alert" className="shrink-0">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </Notice>
      )}
      <Button size="lg" disabled={!canSearch || isSearching} onClick={onSearch} className="h-10 w-full shrink-0">
        {isSearching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
        Search {court.name}
      </Button>
    </Panel>
  );
}
