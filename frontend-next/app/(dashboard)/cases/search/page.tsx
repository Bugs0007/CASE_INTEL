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
  useAdvocateSearchPreference,
  useImportAdvocateCases,
} from "@/hooks/use-advocate-search";
import { useQueryClient } from "@tanstack/react-query";
import { caseKeys } from "@/hooks/use-cases";
import type { AdvocateSearchResult } from "@/types";

const BAR_CODE_RE = /^[A-Za-z]{2,3}\/\d+\/\d{4}$/;

export default function AdvocateSearchPage() {
  const queryClient = useQueryClient();
  const { data: preference } = useAdvocateSearchPreference();

  const [stateCode, setStateCode] = useState("");
  const [distCode, setDistCode] = useState("");
  const [complexValue, setComplexValue] = useState("");
  const [nameOrBarCode, setNameOrBarCode] = useState("");
  const [statusFilter, setStatusFilter] = useState<"Pending" | "Disposed" | "Both">("Both");
  const [formError, setFormError] = useState<string | null>(null);
  const [results, setResults] = useState<AdvocateSearchResult[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [importJobId, setImportJobId] = useState<number | null>(null);

  // Pre-fill state/district from the caller's last search, once -- court
  // complex is left for reselection since the saved hierarchy_config
  // stores the parsed complex_code, not the raw dropdown value the
  // <Select> below needs to match against.
  useEffect(() => {
    if (!preference || stateCode) return;
    setStateCode(preference.hierarchy_config.state_code ?? "");
    setDistCode(preference.hierarchy_config.dist_code ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preference]);

  const states = useCourtStructure({ court_type: "district" });
  const districts = useCourtStructure(
    stateCode ? { court_type: "district", state_code: stateCode } : null,
  );
  const complexes = useCourtStructure(
    stateCode && distCode ? { court_type: "district", state_code: stateCode, dist_code: distCode } : null,
  );

  const complexOption =
    complexValue && complexes.data
      ? (complexes.data.options[complexValue] as { label: string; complex_code?: string; est_code?: string })
      : null;

  const nameLooksLikeBarCode = BAR_CODE_RE.test(nameOrBarCode.trim());
  const nameValid = nameLooksLikeBarCode || nameOrBarCode.trim().length >= 3;
  const canSearch = !!complexOption?.complex_code && nameValid && nameOrBarCode.trim().length > 0;

  const search = useAdvocateSearch();
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
    if (!canSearch || !complexOption) return;

    setResults(null);
    setSelected(new Set());
    setImportJobId(null);

    try {
      const response = await search.mutateAsync({
        name_or_bar_code: nameOrBarCode.trim(),
        court_type: "district",
        hierarchy_config: {
          state_code: stateCode,
          dist_code: distCode,
          court_complex_code: complexOption.complex_code!,
          est_code: complexOption.est_code || "",
        },
        status_filter: statusFilter,
      });
      setResults(response.results);
    } catch (error) {
      if (error instanceof APIError && error.data && typeof error.data === "object") {
        const detail = (error.data as { detail?: string }).detail;
        setFormError(detail || "Could not reach the court portal. Please try again.");
      } else {
        setFormError("Could not reach the court portal. Please try again.");
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
    if (!results || selected.size === 0) return;
    const toAdd = results
      .filter((r) => selected.has(r.cnr_number))
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
    } catch {
      showToast.error("Could not start import", "Please try again.");
    }
  }

  const renderOptions = (options: Record<string, unknown> | undefined) =>
    Object.entries(options || {}).map(([code, value]) => (
      <option key={code} value={code}>
        {typeof value === "string" ? value : (value as { label: string }).label}
      </option>
    ));

  const job = importJob.data;
  const importDone = job?.status === "succeeded" || job?.status === "failed";

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
          Find your cases on eCourts by advocate name or bar registration number, then add the
          ones you want to Case Intel.
        </p>
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5 text-gray-500" />
            District Court
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSearch} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">State</label>
              <Select
                value={stateCode}
                onChange={(e) => {
                  setStateCode(e.target.value);
                  setDistCode("");
                  setComplexValue("");
                }}
                disabled={states.isLoading}
              >
                <option value="">{states.isLoading ? "Loading..." : "Select a state"}</option>
                {renderOptions(states.data?.options)}
              </Select>
            </div>
            {stateCode && (
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">District</label>
                <Select
                  value={distCode}
                  onChange={(e) => {
                    setDistCode(e.target.value);
                    setComplexValue("");
                  }}
                  disabled={districts.isLoading}
                >
                  <option value="">{districts.isLoading ? "Loading..." : "Select a district"}</option>
                  {renderOptions(districts.data?.options)}
                </Select>
              </div>
            )}
            {distCode && (
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Court Complex</label>
                <Select
                  value={complexValue}
                  onChange={(e) => setComplexValue(e.target.value)}
                  disabled={complexes.isLoading}
                >
                  <option value="">{complexes.isLoading ? "Loading..." : "Select a court complex"}</option>
                  {renderOptions(complexes.data?.options)}
                </Select>
              </div>
            )}

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

            {formError && (
              <div className="flex items-start gap-2 rounded-lg bg-[#fdecec] p-3 text-sm text-[#b32e26]">
                <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <span>{formError}</span>
              </div>
            )}

            <Button type="submit" disabled={!canSearch || search.isPending} className="w-full">
              {search.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Searching eCourts...
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  Search
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {results !== null && (
        <Card>
          <CardHeader>
            <CardTitle>{results.length === 0 ? "No Results" : `${results.length} Case(s) Found`}</CardTitle>
          </CardHeader>
          <CardContent>
            {results.length === 0 ? (
              <p className="text-sm text-gray-500">
                No cases found for this advocate/bar code in the selected court.
              </p>
            ) : (
              <>
                <div className="overflow-x-auto rounded-lg border border-gray-100 mb-4">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 text-left text-xs text-gray-500">
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

                <Button
                  onClick={handleAddToMyCases}
                  disabled={selected.size === 0 || startImport.isPending || (importJobId !== null && !importDone)}
                >
                  {startImport.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Starting...
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

      {importJobId !== null && job && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>
              {importDone ? "Import Complete" : `Adding cases... (${job.progress_current}/${job.progress_total})`}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {!importDone && (
              <p className="flex items-center gap-2 text-gray-600">
                <Loader2 className="h-4 w-4 animate-spin" />
                Fetching each selected case from eCourts, one at a time...
              </p>
            )}
            {importDone && (
              <>
                <p className="text-gray-900">{job.created.length} case(s) added.</p>
                {job.skipped_duplicate.length > 0 && (
                  <p className="text-gray-600">
                    {job.skipped_duplicate.length} already in your cases, skipped.
                  </p>
                )}
                {job.skipped_conflict.length > 0 && (
                  <p className="text-gray-600">
                    {job.skipped_conflict.length} already tracked by another user, skipped.
                  </p>
                )}
                {job.failed.length > 0 && (
                  <div className="flex items-start gap-2 rounded-lg bg-[#fdecec] p-3 text-[#b32e26]">
                    <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                    <span>
                      {job.failed.length} case(s) could not be fetched (portal timeout or CAPTCHA) --
                      you can try adding them again.
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
