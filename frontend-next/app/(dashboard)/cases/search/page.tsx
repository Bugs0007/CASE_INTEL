"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Loader2, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { showToast } from "@/components/ui/toaster";
import { APIError } from "@/lib/api/client";
import { useCourtStructure } from "@/hooks/use-case-tracking";
import {
  useAdvocateImportJob,
  useAdvocateSearch,
  useAdvocateSearchJob,
  useAdvocateSearchPreference,
  useImportAdvocateCases,
} from "@/hooks/use-advocate-search";
import { useQueryClient } from "@tanstack/react-query";
import { caseKeys } from "@/hooks/use-cases";
import type { AdvocateSearchResult } from "@/types";

const BAR_CODE_RE = /^[A-Za-z]{2,3}\/\d+\/\d{4}$/;
const IMPORT_CAP = 100;

export default function AdvocateSearchPage() {
  const queryClient = useQueryClient();
  const { data: preference } = useAdvocateSearchPreference();

  const [stateCode, setStateCode] = useState("");
  const [nameOrBarCode, setNameOrBarCode] = useState("");
  const [statusFilter, setStatusFilter] = useState<"Pending" | "Disposed" | "Both">("Both");
  const [formError, setFormError] = useState<string | null>(null);

  const [searchJobId, setSearchJobId] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [importJobId, setImportJobId] = useState<number | null>(null);

  // Pre-fill the state from the caller's last search, once.
  useEffect(() => {
    if (!preference || stateCode) return;
    setStateCode(preference.hierarchy_config.state_code ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preference]);

  const states = useCourtStructure({ court_type: "district" });

  const nameLooksLikeBarCode = BAR_CODE_RE.test(nameOrBarCode.trim());
  const nameValid = nameLooksLikeBarCode || nameOrBarCode.trim().length >= 3;
  const canSearch = !!stateCode && nameValid && nameOrBarCode.trim().length > 0;

  const search = useAdvocateSearch();
  const searchJob = useAdvocateSearchJob(searchJobId);
  const startImport = useImportAdvocateCases();
  const importJob = useAdvocateImportJob(importJobId);

  useEffect(() => {
    if (importJob.data?.status === "succeeded" && importJob.data.created.length > 0) {
      queryClient.invalidateQueries({ queryKey: caseKeys.lists() });
    }
  }, [importJob.data?.status, importJob.data?.created.length, queryClient]);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!canSearch) return;

    setSelected(new Set());
    setImportJobId(null);
    setSearchJobId(null);

    try {
      const { job_id } = await search.mutateAsync({
        name_or_bar_code: nameOrBarCode.trim(),
        court_type: "district",
        state_code: stateCode,
        status_filter: statusFilter,
      });
      setSearchJobId(job_id);
    } catch (error) {
      if (error instanceof APIError && error.data && typeof error.data === "object") {
        const detail = (error.data as { detail?: string }).detail;
        setFormError(detail || "Could not start the search. Please try again.");
      } else {
        setFormError("Could not reach the server. Please try again.");
      }
    }
  }

  function toggleSelected(cnr: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cnr)) next.delete(cnr);
      else next.add(cnr);
      return next;
    });
  }

  async function handleAddToMyCases() {
    const results = searchJob.data?.results ?? [];
    if (selected.size === 0) return;
    const toAdd = results
      .filter((r) => selected.has(r.cnr_number))
      .slice(0, IMPORT_CAP)
      .map((r) => ({
        cnr_number: r.cnr_number,
        case_number: r.case_number,
        petitioner: r.petitioner,
        respondent: r.respondent,
        court_name: r.court_name,
      }));

    try {
      const { job_id } = await startImport.mutateAsync({ courtType: "district", selected: toAdd });
      setImportJobId(job_id);
    } catch (error) {
      if (error instanceof APIError && error.status === 409 && error.data && typeof error.data === "object") {
        const detail = (error.data as { detail?: string }).detail;
        showToast.error("Import already running", detail || "Please wait for the current import to finish.");
      } else {
        showToast.error("Could not start import", "Please try again.");
      }
    }
  }

  const renderOptions = (options: Record<string, unknown> | undefined) =>
    Object.entries(options || {}).map(([code, value]) => (
      <option key={code} value={code}>
        {typeof value === "string" ? value : (value as { label: string }).label}
      </option>
    ));

  const sj = searchJob.data;
  const searchRunning =
    searchJobId !== null && (!sj || sj.status === "queued" || sj.status === "running");
  const results: AdvocateSearchResult[] = sj?.results ?? [];
  const ij = importJob.data;
  const importDone = ij?.status === "succeeded" || ij?.status === "failed";

  return (
    <div className="px-4 sm:px-7 pt-5 sm:pt-7 pb-[60px] max-w-[900px] mx-auto">
      <div className="mb-5">
        <Link
          href="/cases"
          className="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Cases
        </Link>
        <h1 className="text-page-title text-gray-900 mt-2 mb-1.5">Search by Advocate</h1>
        <p className="text-sm text-gray-600">
          Pick a state and enter your advocate name or bar registration number. Case Intel searches
          every district court in that state and gathers all your cases — then you choose which to add.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-gray-500" />
            District Courts — State-wide
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSearch} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">State</label>
              <Select
                value={stateCode}
                onChange={(e) => setStateCode(e.target.value)}
                disabled={states.isLoading}
              >
                <option value="">{states.isLoading ? "Loading..." : "Select a state"}</option>
                {renderOptions(states.data?.options)}
              </Select>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Advocate Name or Bar Code
              </label>
              <Input
                value={nameOrBarCode}
                onChange={(e) => setNameOrBarCode(e.target.value)}
                placeholder="e.g. Suresh Kumar, or MAH/1234/2015"
              />
              {nameOrBarCode && !nameValid && (
                <p className="mt-1 text-xs text-gray-500">
                  Enter at least 3 characters of a name, or a bar code in STATE/NUMBER/YEAR format.
                </p>
              )}
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Case Status</label>
              <div className="flex gap-4 text-sm">
                {(["Pending", "Disposed", "Both"] as const).map((option) => (
                  <label key={option} className="flex items-center gap-1.5">
                    <input
                      type="radio"
                      name="status_filter"
                      checked={statusFilter === option}
                      onChange={() => setStatusFilter(option)}
                    />
                    {option}
                  </label>
                ))}
              </div>
            </div>

            <div className="flex items-start gap-2 rounded-lg bg-[#ebf3fb] border border-[#d6e7f7] p-3 text-xs text-[#2f6fb0]">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>
                A state-wide search checks every district and court complex, one at a time, and can
                take <strong>several minutes</strong> (longer for large states). You can leave this
                page open — progress is shown below.
              </span>
            </div>

            {formError && (
              <div className="flex items-start gap-2 rounded-lg bg-[#fdecec] p-3 text-sm text-[#b32e26]">
                <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span>{formError}</span>
              </div>
            )}

            <Button
              type="submit"
              disabled={!canSearch || search.isPending || searchRunning}
              className="w-full"
            >
              {search.isPending || searchRunning ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Searching…
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  Search State-wide
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {searchJobId !== null && sj && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>
              {searchRunning
                ? `Searching… (${sj.progress_current}/${sj.progress_total || "?"} districts)`
                : sj.status === "failed"
                  ? "Search failed"
                  : `${results.length} Case(s) Found`}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {searchRunning && (
              <>
                <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100 mb-2">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{
                      width: sj.progress_total
                        ? `${Math.round((sj.progress_current / sj.progress_total) * 100)}%`
                        : "10%",
                    }}
                  />
                </div>
                <p className="flex items-center gap-2 text-sm text-gray-600">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Checking every district in the state — this can take several minutes.
                </p>
              </>
            )}

            {sj.status === "failed" && (
              <div className="flex items-start gap-2 rounded-lg bg-[#fdecec] p-3 text-sm text-[#b32e26]">
                <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span>{sj.error || "The court portal could not be reached. Please try again."}</span>
              </div>
            )}

            {sj.status === "succeeded" && results.length === 0 && (
              <p className="text-sm text-gray-500">
                No cases found for this advocate/bar code anywhere in the selected state.
              </p>
            )}

            {sj.status === "succeeded" && results.length > 0 && (
              <>
                {sj.failures.length > 0 && (
                  <div className="mb-3 flex items-start gap-2 rounded-lg bg-[#fdf3e0] border border-[#f5e3c2] p-3 text-xs text-[#92610f]">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                    <span>
                      {sj.failures.length} court(s) couldn&apos;t be searched (CAPTCHA or portal
                      timeout) and were skipped — results may be partial. Re-run to retry them.
                    </span>
                  </div>
                )}
                <div className="max-h-[480px] overflow-auto rounded-lg border border-gray-100 mb-4">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0 bg-gray-50 text-left text-xs text-gray-500">
                      <tr>
                        <th className="px-3 py-2 w-8"></th>
                        <th className="px-3 py-2 font-medium">Case Number</th>
                        <th className="px-3 py-2 font-medium">Parties</th>
                        <th className="px-3 py-2 font-medium">Court</th>
                        <th className="px-3 py-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {results.map((r) => (
                        <tr key={r.cnr_number}>
                          <td className="px-3 py-2">
                            <input
                              type="checkbox"
                              checked={selected.has(r.cnr_number)}
                              onChange={() => toggleSelected(r.cnr_number)}
                            />
                          </td>
                          <td className="px-3 py-2 font-mono whitespace-nowrap">{r.case_number}</td>
                          <td className="px-3 py-2 text-gray-700">
                            {r.petitioner || "—"} vs {r.respondent || "—"}
                          </td>
                          <td className="px-3 py-2 text-gray-600">{r.court_name || "—"}</td>
                          <td className="px-3 py-2 text-gray-600">{r.status || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {selected.size > IMPORT_CAP && (
                  <p className="mb-2 text-xs text-[#b32e26]">
                    You can add up to {IMPORT_CAP} at a time — only the first {IMPORT_CAP} selected
                    will be added.
                  </p>
                )}
                <Button
                  onClick={handleAddToMyCases}
                  disabled={selected.size === 0 || startImport.isPending || (importJobId !== null && !importDone)}
                >
                  {startImport.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Starting…
                    </>
                  ) : (
                    `Add ${selected.size || ""} to My Cases`
                  )}
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      )}

      {importJobId !== null && ij && (
        <Card>
          <CardHeader>
            <CardTitle>
              {importDone ? "Import Complete" : `Adding cases… (${ij.progress_current}/${ij.progress_total})`}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!importDone && (
              <p className="flex items-center gap-2 text-gray-600">
                <Loader2 className="h-4 w-4 animate-spin" />
                Fetching each selected case from eCourts, one at a time…
              </p>
            )}
            {importDone && (
              <>
                <p className="text-gray-900">{ij.created.length} case(s) added.</p>
                {ij.skipped_duplicate.length > 0 && (
                  <p className="text-gray-600">
                    {ij.skipped_duplicate.length} already in your cases, skipped.
                  </p>
                )}
                {ij.skipped_conflict.length > 0 && (
                  <p className="text-gray-600">
                    {ij.skipped_conflict.length} already tracked by another user, skipped.
                  </p>
                )}
                {ij.failed.length > 0 && (
                  <div className="flex items-start gap-2 rounded-lg bg-[#fdecec] p-3 text-[#b32e26]">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                    <span>
                      {ij.failed.length} case(s) could not be fetched (portal timeout or CAPTCHA) —
                      you can select them again and retry.
                    </span>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
