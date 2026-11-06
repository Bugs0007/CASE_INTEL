"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Gavel, Loader2, RotateCcw, Scale } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ConflictWarning } from "@/components/cases/conflict-warning";
import { showToast } from "@/components/ui/toaster";
import { advocateSearchKeys, useAdvocateImportJob, useAdvocateSearchJob, useAdvocateSearchPreference, useImportAdvocateCases } from "@/hooks/use-advocate-search";
import {
  useActiveSearches,
  useAdvocateProfiles,
  useCancelSearch,
  useCourtsStatus,
  useHighCourtBenches,
  useHighCourts,
  useNameAction,
  useRetryCourts,
  useStartSearchV2,
} from "@/hooks/use-advocate-search-v2";
import { useCourtStructure } from "@/hooks/use-case-tracking";
import { caseKeys, useCases } from "@/hooks/use-cases";
import { useNow } from "@/hooks/use-now";
import { coverageOf } from "@/lib/hc-jurisdiction";
import {
  activeFilterLabels,
  applyFilters,
  DEFAULT_FILTERS,
  filtersFromParams,
  filtersToParams,
  formatClock,
  type ResultFilters,
} from "@/lib/advocate-search-results";
import { cn, pluralize } from "@/lib/utils";
import type { AdvocateFeatures, AdvocateResultRow, AdvocateSearchProfile } from "@/types";
import { CourtComplexStatus } from "./court-complex-status";
import { DistrictPicker, type StatusFilter } from "./district-picker";
import { apiErrorText } from "./errors";
import { HighCourtPicker } from "./high-court-picker";
import { HighCourtForm } from "./high-court-tab-form";
import { ImportBar } from "./import-bar";
import { LiveMatches } from "./live-matches";
import { CreateProfileCard, AdvocateProfileCard } from "./profile-card";
import { ResultFiltersBar } from "./result-filters";
import { pickListedName, ResultsTable } from "./results-table";
import { SearchProgress } from "./search-progress";
import { Notice } from "./ui";

const IMPORT_CAP = 100;
type Tab = "district" | "hc";

const label = (value: unknown): string => (typeof value === "string" ? value : ((value as { label?: string })?.label ?? ""));
const joinNames = (names: string[]) =>
  names.length <= 1 ? (names[0] ?? "") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;

/** The redesigned "Find cases by advocate" page. The URL holds what is needed to
 * come back to the same screen: ?tab=, ?job= (a running or finished search), the
 * result filters and the chosen High Court. */
export function AdvocateSearchV2({ features }: { features: AdvocateFeatures }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const queryClient = useQueryClient();

  const jobParam = Number(params.get("job"));
  const jobId = Number.isInteger(jobParam) && jobParam > 0 ? jobParam : null;
  const filters = useMemo(() => filtersFromParams(new URLSearchParams(params.toString())), [params]);

  const update = (patch: Record<string, string | null>, filterPatch?: ResultFilters) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (v === null) next.delete(k);
      else next.set(k, v);
    }
    if (filterPatch) filtersToParams(filterPatch, next);
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  // ---- the profile ---------------------------------------------------------
  const profiles = useAdvocateProfiles();
  const profile: AdvocateSearchProfile | undefined = profiles.data?.[0];

  // ---- a search in progress or finished ------------------------------------
  const courtsQ = useCourtsStatus(jobId);
  const jobQ = useAdvocateSearchJob(jobId, !!courtsQ.data?.job.is_retrying);
  const sj = jobQ.data;
  const courts = courtsQ.data;
  const jobCourtType = sj?.court_type ?? "district";
  const tab: Tab = jobId !== null && sj ? (jobCourtType === "high_court" ? "hc" : "district") : params.get("tab") === "hc" ? "hc" : "district";

  // Reopen a search the advocate left running, once, when the page opens with none.
  const resumed = useRef(false);
  const active = useActiveSearches(jobId === null && !resumed.current);
  useEffect(() => {
    if (jobId === null && !resumed.current && active.data) {
      resumed.current = true;
      if (active.data.length > 0) update({ job: String(active.data[0].job_id) });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active.data, jobId]);

  // A job that is not this advocate's (or is gone) is dropped, not left spinning.
  useEffect(() => {
    if (jobId !== null && (jobQ.isError || courtsQ.isError) && !sj) update({ job: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobQ.isError, courtsQ.isError]);

  const running = jobId !== null && (!sj || sj.status === "queued" || sj.status === "running" || !!courts?.job.is_retrying);
  const now = useNow(running);

  // ---- the district form ---------------------------------------------------
  const preference = useAdvocateSearchPreference();
  const [stateCode, setStateCode] = useState("");
  const [distCodes, setDistCodes] = useState<string[]>([]);
  const [status, setStatus] = useState<StatusFilter>("Both");
  const [searchBy, setSearchBy] = useState<"names" | "bar_code">("names");
  const [formError, setFormError] = useState("");
  const prefilled = useRef(false);
  useEffect(() => {
    if (preference.data && !prefilled.current) {
      prefilled.current = true;
      setStateCode(preference.data.hierarchy_config.state_code ?? "");
      setDistCodes(preference.data.hierarchy_config.dist_codes ?? []);
    }
  }, [preference.data]);
  const profileBarCode = profile?.bar_codes[0] ?? "";
  const barCodeAvailable = useRef(false);
  useEffect(() => {
    // Default to the bar number once a profile has one (exact and fastest).
    if (profile && !barCodeAvailable.current) {
      barCodeAvailable.current = true;
      setSearchBy(profileBarCode ? "bar_code" : "names");
    }
  }, [profile, profileBarCode]);

  const states = useCourtStructure({ court_type: "district" });
  const stateName = label(states.data?.options?.[sj?.state_code || stateCode]);

  // ---- the High Court form -------------------------------------------------
  const highCourts = useHighCourts();
  const courtCode = params.get("court");
  const court = highCourts.data?.find((c) => c.code === courtCode) ?? null;
  const benchesQ = useHighCourtBenches(court?.supported ? court.code : null);
  const benches = useMemo(() => benchesQ.data?.benches ?? [], [benchesQ.data]);
  const [chosenBenches, setChosenBenches] = useState<string[]>([]);
  useEffect(() => {
    setChosenBenches(benches.filter((b) => b.default).map((b) => b.code));
  }, [benches]);
  const [hcStatus, setHcStatus] = useState<StatusFilter>("Both");
  const [hcSearchBy, setHcSearchBy] = useState<"names" | "bar_code">("names");
  useEffect(() => setHcSearchBy(profileBarCode ? "bar_code" : "names"), [profileBarCode]);

  // ---- starting a search ---------------------------------------------------
  const start = useStartSearchV2();
  const begin = async (body: Parameters<typeof start.mutateAsync>[0], tabName: Tab) => {
    setFormError("");
    setSelected(new Set());
    try {
      const res = await start.mutateAsync(body);
      update({ job: String(res.job_id), tab: tabName });
      if (res.warning) showToast.warning("Name search on a High Court", res.warning);
    } catch (error) {
      setFormError(apiErrorText(error, "Could not start the search. Please try again."));
    }
  };

  // ---- results -------------------------------------------------------------
  const rows: AdvocateResultRow[] = useMemo(() => sj?.results ?? [], [sj]);
  const counts = sj?.match_counts ?? {};
  const shown = useMemo(() => applyFilters(rows, filters), [rows, filters]);
  // What the filters (search, status, court, year, match) take out of the list, apart from the Show hidden switches.
  const activeFilters = useMemo(() => activeFilterLabels(filters), [filters]);
  const withoutFilters = useMemo(
    () => applyFilters(rows, { ...DEFAULT_FILTERS, showExcluded: filters.showExcluded, showOther: filters.showOther }).length,
    [rows, filters.showExcluded, filters.showOther],
  );
  const clearFilters = () => update({}, { ...DEFAULT_FILTERS, showExcluded: filters.showExcluded, showOther: filters.showOther });
  const cases = useCases();
  const inCases = useMemo(() => new Set((cases.data ?? []).map((c) => c.cnr_number).filter((n): n is string => !!n)), [cases.data]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const nameAction = useNameAction(jobId);
  const retry = useRetryCourts(jobId);
  const cancel = useCancelSearch(jobId);
  const startImport = useImportAdvocateCases();
  const [importJobId, setImportJobId] = useState<number | null>(null);
  const importJob = useAdvocateImportJob(importJobId);
  const ij = importJob.data;
  const importDone = ij?.status === "succeeded" || ij?.status === "failed";
  useEffect(() => {
    if (ij?.status === "succeeded" && ij.created.length > 0) queryClient.invalidateQueries({ queryKey: caseKeys.lists() });
  }, [ij?.status, ij?.created.length, queryClient]);
  useEffect(() => {
    if (sj?.status === "succeeded") queryClient.invalidateQueries({ queryKey: advocateSearchKeys.preference });
  }, [sj?.status, queryClient]);

  const toggle = (cnr: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cnr)) next.delete(cnr);
      else next.add(cnr);
      return next;
    });
  const selectable = shown.filter((r) => !inCases.has(r.cnr_number));
  const verified = rows.filter((r) => r.match_status === "matched" && !inCases.has(r.cnr_number));
  const skipped = [...selected].filter((cnr) => inCases.has(cnr)).length;
  const chosen = rows.filter((r) => selected.has(r.cnr_number) && !inCases.has(r.cnr_number));

  const doImport = async () => {
    const toAdd = chosen.slice(0, IMPORT_CAP).map((r) => ({
      cnr_number: r.cnr_number,
      case_number: r.case_number,
      petitioner: r.petitioner,
      respondent: r.respondent,
      court_name: r.complex_name || r.court_name,
    }));
    try {
      const { job_id } = await startImport.mutateAsync({
        courtType: jobCourtType === "high_court" ? "high_court" : "district",
        selected: toAdd,
        searchJobId: jobId ?? undefined,
      });
      setImportJobId(job_id);
      setSelected(new Set());
    } catch (error) {
      showToast.error("Could not start the import", apiErrorText(error, "Please try again."));
    }
  };

  const onNameAction = (row: AdvocateResultRow, action: "exclude" | "add") => {
    if (!profile) return;
    const name = pickListedName(row);
    nameAction.mutate(
      { profileId: profile.id, name, action },
      {
        onSuccess: () => showToast.success(action === "exclude" ? `${name}: not you` : `${name}: yours`, "The list changed; nothing was searched again."),
        onError: (error) => showToast.error("Could not save that", apiErrorText(error, "Please try again.")),
      },
    );
  };

  const doRetry = (body: { only_failed: true } | { complex_ids: number[] }) =>
    retry.mutate(body, {
      onSuccess: (res) => showToast.info(`Searching ${pluralize(res.courts, "court")} again`, "What they find joins this list."),
      onError: (error) => showToast.error("Could not retry", apiErrorText(error, "Please try again.")),
    });

  // ---- what to show --------------------------------------------------------
  const newSearch = () => {
    setSelected(new Set());
    setImportJobId(null);
    update({ job: null }, { ...filters, q: "", status: "all", court: "", yearFrom: null, yearTo: null, match: "all", showExcluded: false, showOther: false });
  };
  const goTab = (t: Tab) => {
    if (jobId !== null) {
      setSelected(new Set());
      update({ job: null, tab: t });
    } else update({ tab: t });
  };

  const district = tab === "district";
  const names = courts ? courts.groups.map((g) => g.name) : [];
  const runningTitle = jobCourtType === "high_court" ? `Searching ${sj?.hc_court_name || "the High Court"}` : `Searching ${joinNames(names) || "…"}`;
  const startedAt = courts?.job.started_at ?? courts?.job.created_at;
  const lastFinished = courts?.groups.flatMap((g) => g.runs).map((r) => r.finished_at).filter((t): t is string => !!t).sort().pop();
  const elapsedSeconds = startedAt ? ((running ? now : lastFinished ? Date.parse(lastFinished) : now) - Date.parse(startedAt)) / 1000 : 0;
  const visibleFound = rows.filter((r) => r.match_status === "matched" || r.match_status === "check" || !r.match_status);
  const hiddenExcluded = counts.excluded ?? 0;
  const matchedCount = counts.matched ?? 0;
  const checkCount = counts.check ?? 0;
  const allFailed = !!courts && courts.counts.total > 0 && courts.counts.done === 0 && courts.counts.failed === courts.counts.total;

  return (
    <div className="flex h-full min-h-0 flex-col bg-page">
      <div className="flex shrink-0 flex-wrap items-end gap-4 border-b border-gray-200 bg-surface px-6 pt-3.5">
        <div className="pb-2.5">
          <Link href="/cases" className="text-xs text-gray-500 hover:text-gray-900">
            ← Back to Cases
          </Link>
          <h1 className="font-serif text-2xl font-bold leading-tight text-gray-900">Find cases by advocate</h1>
          <p className="text-[13px] text-gray-600">Search a court for every case an advocate appears in, then import the ones that are yours.</p>
        </div>
        <div role="tablist" aria-label="Court type" className="ml-auto flex gap-0.5">
          {(
            [
              ["district", "District courts", Scale],
              ["hc", "High Courts", Gavel],
            ] as const
          ).map(([value, text, Icon]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={tab === value}
              onClick={() => goTab(value)}
              className={cn(
                "flex items-center gap-2 border-b-[3px] px-[18px] py-2.5 text-[13.5px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary",
                tab === value ? "border-primary text-gray-900" : "border-transparent text-gray-500 hover:text-gray-800",
              )}
            >
              <Icon className="h-4 w-4" />
              {text}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-6 py-4 lg:overflow-hidden">
        {/* ---- the form ---- */}
        {jobId === null && district && (
          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
            {profiles.isLoading ? (
              <p className="flex items-center gap-2 text-sm text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading your profile…
              </p>
            ) : profiles.isError ? (
              <Notice tone="alert" className="lg:col-span-2">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  Your advocate profile did not load.{" "}
                  <button type="button" className="font-semibold underline" onClick={() => profiles.refetch()}>
                    Retry
                  </button>
                </span>
              </Notice>
            ) : (
              <>
                {profile ? <AdvocateProfileCard profile={profile} /> : <CreateProfileCard />}
                <DistrictPicker
                  stateCode={stateCode}
                  onStateChange={setStateCode}
                  distCodes={distCodes}
                  onDistCodesChange={setDistCodes}
                  status={status}
                  onStatusChange={setStatus}
                  searchBy={searchBy}
                  onSearchByChange={setSearchBy}
                  hasBarCode={!!profileBarCode}
                  queryCount={profile?.query_count ?? 0}
                  secondsPerCall={features.seconds_per_call}
                  canSearch={!!profile && !!stateCode && (searchBy === "bar_code" ? !!profileBarCode : (profile?.query_count ?? 0) > 0)}
                  isSearching={start.isPending}
                  error={formError}
                  onSearch={() =>
                    profile &&
                    begin(
                      {
                        profile_id: profile.id,
                        court_type: "district",
                        state_code: stateCode,
                        dist_codes: distCodes,
                        status_filter: status,
                        search_by: searchBy,
                        bar_code: searchBy === "bar_code" ? profileBarCode : undefined,
                      },
                      "district",
                    )
                  }
                />
              </>
            )}
          </div>
        )}

        {jobId === null && !district && (
          <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <HighCourtPicker
              courts={highCourts.data ?? []}
              selected={court?.code ?? null}
              onSelect={(code) => update({ court: code })}
              loadError={highCourts.isError}
              onRetry={() => highCourts.refetch()}
            />
            {profile ? (
              <HighCourtForm
                court={court}
                benches={benches}
                benchesLoading={benchesQ.isLoading}
                benchesError={benchesQ.isError}
                onRetryBenches={() => benchesQ.refetch()}
                chosenBenches={chosenBenches}
                onChosenBenches={setChosenBenches}
                status={hcStatus}
                onStatusChange={setHcStatus}
                searchBy={hcSearchBy}
                onSearchByChange={setHcSearchBy}
                profile={profile}
                yearFrom={filters.yearFrom}
                yearTo={filters.yearTo}
                onYearChange={(from, to) => update({}, { ...filters, yearFrom: from, yearTo: to })}
                secondsPerCall={features.seconds_per_call}
                isSearching={start.isPending}
                error={formError}
                coverage={court ? coverageOf(court.code) : ""}
                onSearch={() =>
                  court &&
                  begin(
                    {
                      profile_id: profile.id,
                      court_type: "high_court",
                      hc_court_code: court.code,
                      bench_codes: chosenBenches,
                      status_filter: hcStatus,
                      search_by: hcSearchBy,
                      bar_code: hcSearchBy === "bar_code" ? profileBarCode : undefined,
                    },
                    "hc",
                  )
                }
              />
            ) : (
              <CreateProfileCard />
            )}
          </div>
        )}

        {/* ---- running ---- */}
        {jobId !== null && running && (
          <>
            {courts ? (
              <SearchProgress
                title={runningTitle}
                courts={courts}
                elapsedSeconds={elapsedSeconds}
                matchedSoFar={matchedCount + checkCount}
                onStop={() => cancel.mutate()}
                stopping={cancel.isPending}
              />
            ) : (
              <p className="flex items-center gap-2 text-sm text-gray-500">
                <Loader2 className="h-4 w-4 animate-spin" /> Opening the search…
              </p>
            )}
            {courts && (
              <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
                <CourtComplexStatus
                  courts={courts}
                  retrying={retry.isPending}
                  onRetryOne={(id) => doRetry({ complex_ids: [id] })}
                  onRetryFailed={() => doRetry({ only_failed: true })}
                />
                <LiveMatches rows={visibleFound} hiddenCount={hiddenExcluded} />
              </div>
            )}
          </>
        )}

        {/* ---- finished ---- */}
        {jobId !== null && !running && sj && (
          <>
            <div className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-gray-200 bg-surface px-4 py-2.5">
              <div className="min-w-0">
                <h2 className="truncate font-serif text-lg font-bold text-gray-900">
                  {matchedCount + checkCount} {matchedCount + checkCount === 1 ? "case" : "cases"} for {profile?.display_name ?? "this advocate"}
                </h2>
                <p className="truncate text-xs text-gray-500">
                  {[jobCourtType === "high_court" ? sj.hc_court_name : stateName, joinNames(names), courts && elapsedSeconds > 0 ? `done in ${formatClock(elapsedSeconds)}` : ""]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <span className="flex-1" />
              <p className="flex gap-5 text-[13px] text-gray-600">
                <span>
                  <b className="text-[15px] font-semibold text-gray-900">{matchedCount}</b> match your names
                </span>
                <span className="text-status-pending">
                  <b className="text-[15px] font-semibold">{checkCount}</b> need a check
                </span>
                <span>
                  <b className="text-[15px] font-semibold text-gray-900">{hiddenExcluded}</b> hidden (Not me)
                </span>
                {activeFilters.length > 0 && (
                  <span className="text-status-pending" data-testid="filtered-count">
                    Showing <b className="text-[15px] font-semibold">{shown.length}</b> of {withoutFilters} (filtered)
                  </span>
                )}
              </p>
              <Button variant="secondary" size="sm" onClick={newSearch}>
                <RotateCcw className="h-3 w-3" />
                Search again
              </Button>
            </div>

            {sj.status === "failed" && (
              <Notice tone="alert" className="shrink-0">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  {sj.error || "The court portal could not be reached."} Nothing was found, which is not the same as no cases. Search again in a
                  few minutes.
                </span>
              </Notice>
            )}
            {allFailed && sj.status !== "failed" && (
              <Notice tone="alert" className="shrink-0">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>
                  No court could be read: the portal is refusing or dropping requests right now. Nothing was found, which is not the same as no
                  cases.{" "}
                  {courts?.job.can_retry && (
                    <button type="button" className="font-semibold underline" onClick={() => doRetry({ only_failed: true })}>
                      Search them all again
                    </button>
                  )}
                </span>
              </Notice>
            )}
            {courts && courts.needs_attention.length > 0 && !allFailed && (
              <Notice tone="warn" className="shrink-0 items-center">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                <span className="flex-1">
                  {pluralize(courts.needs_attention.length, "court")} could not be read and{" "}
                  {courts.needs_attention.length === 1 ? "is" : "are"} not in this list (
                  {joinNames(courts.needs_attention.map((c) => c.complex_name)).slice(0, 140)}).
                </span>
                {courts.job.can_retry && (
                  <Button size="sm" onClick={() => doRetry({ only_failed: true })} disabled={retry.isPending}>
                    Retry {courts.needs_attention.length}
                  </Button>
                )}
                <a href={courts.court_site_url} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1 font-semibold underline">
                  Open the court site <ExternalLink className="h-3 w-3" />
                </a>
              </Notice>
            )}
            {sj.results_truncated && (
              <Notice tone="warn" className="shrink-0">
                Showing the best {rows.length.toLocaleString()} of {sj.results_total.toLocaleString()} rows, your own first. Narrow the search to see the rest.
              </Notice>
            )}

            {rows.length === 0 && sj.status !== "failed" && !allFailed ? (
              <div className="grid flex-1 place-items-center rounded-lg border border-dashed border-gray-300 bg-surface p-8 text-center">
                <p className="max-w-md text-sm text-gray-600">
                  The courts that answered returned no rows for this {jobCourtType === "high_court" ? "bench" : "search"}.
                  {courts && courts.needs_attention.length > 0 ? " Some courts could not be read, so this may not be the whole picture." : ""}
                </p>
              </div>
            ) : (
              rows.length > 0 && (
                <>
                  <ResultFiltersBar filters={filters} onChange={(next) => update({}, next)} rows={rows} counts={counts} />
                  {matchedCount + checkCount === 0 && hiddenExcluded + (counts.other ?? 0) > 0 && !filters.showExcluded && !filters.showOther && (
                    <Notice className="shrink-0">
                      Every row the courts returned is on your Not me list or lists another advocate. Open Show hidden to see them.
                    </Notice>
                  )}
                  {ij && (
                    <Notice tone={ij.failed.length > 0 ? "warn" : "info"} className="shrink-0">
                      <span>
                        {!importDone ? (
                          <>
                            <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" />
                            Adding cases… ({ij.progress_current}/{ij.progress_total})
                          </>
                        ) : (
                          <>
                            {ij.created.length} added.
                            {ij.skipped_duplicate.length > 0 && ` ${ij.skipped_duplicate.length} already in Cases, skipped.`}
                            {ij.failed.length > 0 && ` ${ij.failed.length} could not be fetched (portal timeout or CAPTCHA); tick them and import again.`}
                          </>
                        )}
                      </span>
                    </Notice>
                  )}
                  {ij && importDone && Object.keys(ij.conflicts ?? {}).length > 0 && (
                    <ConflictWarning
                      conflicts={Object.values(ij.conflicts).flat()}
                      title={`${Object.keys(ij.conflicts).length} imported case(s) may conflict with cases you already have. They were added, and each is noted on its activity log.`}
                    />
                  )}
                  <ResultsTable
                    rows={shown}
                    selected={selected}
                    inCases={inCases}
                    onToggle={toggle}
                    onToggleAll={() =>
                      setSelected((prev) => (selectable.every((r) => prev.has(r.cnr_number)) ? new Set() : new Set(selectable.map((r) => r.cnr_number))))
                    }
                    onNameAction={onNameAction}
                    showStatus={rows.some((r) => !!r.status)}
                    activeFilters={activeFilters}
                    hiddenByFilters={withoutFilters - shown.length}
                    onClearFilters={clearFilters}
                  />
                  <ImportBar
                    selectedCount={chosen.length}
                    skippedCount={skipped}
                    verifiedCount={verified.length}
                    onSelectVerified={() => setSelected(new Set(verified.map((r) => r.cnr_number)))}
                    onImport={doImport}
                    importing={startImport.isPending || (importJobId !== null && !importDone)}
                    cap={IMPORT_CAP}
                  />
                </>
              )
            )}
          </>
        )}
      </div>
    </div>
  );
}
