"use client";

import { useMemo, useState } from "react";
import {
  Gavel,
  Loader2,
  ExternalLink,
  RefreshCw,
  AlertTriangle,
  CalendarClock,
  Trash2,
  Search,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Collapsible } from "@/components/ui/collapsible";
import { showToast } from "@/components/ui/toaster";
import { APIError } from "@/lib/api/client";
import { formatDate, formatRelativeTime } from "@/lib/utils";
import {
  useConfirmTracking,
  useCourtStructure,
  usePreviewTracking,
  useRefreshTracking,
  useUntrackTracking,
} from "@/hooks/use-case-tracking";
import type { Case, CourtType, Hearing, TrackingConfig, TrackingPreview } from "@/types";

const DISTRICT_PORTAL_URL = "https://services.ecourts.gov.in/ecourtindia_v6/";
const HC_PORTAL_URL = "https://hcservices.ecourts.gov.in/hcservices/";

interface CourtTrackingCardProps {
  caseItem: Case;
  hearings: Hearing[];
}

export function CourtTrackingCard({ caseItem, hearings }: CourtTrackingCardProps) {
  if (!caseItem.tracking_enabled) {
    return <TrackingSetupForm caseId={caseItem.id} />;
  }
  return <TrackingDisplay caseItem={caseItem} hearings={hearings} />;
}

// ---------------------------------------------------------------------------
// Setup flow
// ---------------------------------------------------------------------------

function TrackingSetupForm({ caseId }: { caseId: number }) {
  const [mode, setMode] = useState<"cnr" | "cascade">("cnr");
  const [cnr, setCnr] = useState("");
  const [cnrCourtType, setCnrCourtType] = useState<CourtType>("district");

  const [courtType, setCourtType] = useState<CourtType>("district");
  const [stateCode, setStateCode] = useState("");
  const [distCode, setDistCode] = useState("");
  const [complexValue, setComplexValue] = useState("");
  const [hcCourtCode, setHcCourtCode] = useState("");
  const [benchCode, setBenchCode] = useState("");
  const [caseTypeCode, setCaseTypeCode] = useState("");
  const [caseNumber, setCaseNumber] = useState("");
  const [year, setYear] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [preview, setPreview] = useState<TrackingPreview | null>(null);

  const previewTracking = usePreviewTracking(caseId);
  const confirmTracking = useConfirmTracking(caseId);

  // Cascading discovery calls -- each only fires once its prerequisite is set.
  const states = useCourtStructure(courtType === "district" ? { court_type: "district" } : null);
  const districts = useCourtStructure(
    courtType === "district" && stateCode ? { court_type: "district", state_code: stateCode } : null,
  );
  const complexes = useCourtStructure(
    courtType === "district" && stateCode && distCode
      ? { court_type: "district", state_code: stateCode, dist_code: distCode }
      : null,
  );
  const hcCourts = useCourtStructure(courtType === "high_court" ? { court_type: "high_court" } : null);
  const benches = useCourtStructure(
    courtType === "high_court" && hcCourtCode ? { court_type: "high_court", hc_court_code: hcCourtCode } : null,
  );

  const complexOption =
    complexValue && complexes.data
      ? (complexes.data.options[complexValue] as { label: string; complex_code?: string; est_code?: string })
      : null;

  const caseTypes = useCourtStructure(
    courtType === "district" && complexOption?.complex_code
      ? {
          court_type: "district",
          state_code: stateCode,
          dist_code: distCode,
          court_complex_code: complexOption.complex_code,
          est_code: complexOption.est_code,
        }
      : courtType === "high_court" && hcCourtCode && benchCode
        ? { court_type: "high_court", hc_court_code: hcCourtCode, bench_code: benchCode }
        : null,
  );

  const cnrValid = cnr.trim().length === 16 && /^[a-zA-Z0-9]+$/.test(cnr.trim());
  const canSubmitCascade =
    caseTypeCode &&
    caseNumber &&
    year &&
    (courtType === "district" ? complexOption?.complex_code : hcCourtCode && benchCode);
  const canSubmit = mode === "cnr" ? cnrValid : canSubmitCascade;

  function resetDownstream(level: "courtType" | "state" | "district" | "hcCourt") {
    if (level === "courtType") {
      setStateCode("");
      setDistCode("");
      setComplexValue("");
      setHcCourtCode("");
      setBenchCode("");
    }
    if (level === "state") {
      // Don't touch distCode here beyond clearing it -- setting it to the
      // pre-change closure value (a stale-closure bug caught by browser
      // testing) silently undid the selection that just happened.
      setDistCode("");
      setComplexValue("");
    }
    if (level === "district") {
      setComplexValue("");
    }
    if (level === "hcCourt") {
      setBenchCode("");
    }
    setCaseTypeCode("");
  }

  async function handlePreviewSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!canSubmit) return;

    const config: TrackingConfig =
      mode === "cnr"
        ? { court_type: cnrCourtType, cnr: cnr.trim().toUpperCase() }
        : courtType === "district"
          ? {
              court_type: "district",
              state_code: stateCode,
              dist_code: distCode,
              court_complex_code: complexOption!.complex_code!,
              est_code: complexOption!.est_code || "",
              case_type: caseTypeCode,
              case_number: caseNumber,
              year,
            }
          : {
              court_type: "high_court",
              hc_court_code: hcCourtCode,
              bench_code: benchCode,
              case_type: caseTypeCode,
              case_number: caseNumber,
              year,
            };

    try {
      const result = await previewTracking.mutateAsync(config);
      setPreview(result);
    } catch (error) {
      if (error instanceof APIError && error.data && typeof error.data === "object") {
        const detail = (error.data as { detail?: string }).detail;
        setFormError(detail || "Could not fetch this case. Please check the details and try again.");
      } else {
        setFormError("Could not reach the court portal. Please try again.");
      }
    }
  }

  async function handleConfirm() {
    if (!preview) return;
    try {
      await confirmTracking.mutateAsync(preview.preview_token);
      showToast.success("Tracking enabled", "Case confirmed and tracking started.");
    } catch (error) {
      // Most likely a 410 (preview expired) -- send the user back to the
      // form rather than leaving them stuck on a dead preview panel.
      setPreview(null);
      if (error instanceof APIError && error.data && typeof error.data === "object") {
        const detail = (error.data as { detail?: string }).detail;
        setFormError(detail || "This preview expired. Please search again.");
      } else {
        setFormError("Could not save this case. Please search again.");
      }
    }
  }

  function handleTryAgain() {
    setPreview(null);
    // Inputs are intentionally left as-is -- Try Again returns to the
    // form with prior inputs retained, not a blank form.
  }

  const renderOptions = (options: Record<string, unknown> | undefined) =>
    Object.entries(options || {}).map(([code, value]) => (
      <option key={code} value={code}>
        {typeof value === "string" ? value : (value as { label: string }).label}
      </option>
    ));

  if (preview) {
    return (
      <TrackingPreviewPanel
        preview={preview}
        onConfirm={handleConfirm}
        onTryAgain={handleTryAgain}
        isConfirming={confirmTracking.isPending}
        error={formError}
      />
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Gavel className="h-5 w-5 text-gray-500" />
          Court Tracking
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-gray-600 mb-4">
          {mode === "cnr"
            ? "Enter the case's CNR number to fetch it directly -- no need to know the court hierarchy or case number."
            : "Search by court, case type, number, and year. The CNR is captured automatically once the case is found."}
        </p>

        <div className="mb-4 flex gap-2 text-sm">
          <button
            type="button"
            onClick={() => {
              setMode("cnr");
              setFormError(null);
            }}
            className={`rounded-full px-3 py-1 font-medium transition-colors ${
              mode === "cnr" ? "bg-primary text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            Have a CNR
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("cascade");
              setFormError(null);
            }}
            className={`rounded-full px-3 py-1 font-medium transition-colors ${
              mode === "cascade" ? "bg-primary text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
            }`}
          >
            Search by case number
          </button>
        </div>

        <form onSubmit={handlePreviewSubmit} className="space-y-4">
          {mode === "cnr" ? (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Court</label>
                <Select value={cnrCourtType} onChange={(e) => setCnrCourtType(e.target.value as CourtType)}>
                  <option value="district">District Court</option>
                  <option value="high_court">High Court</option>
                </Select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">CNR Number</label>
                <Input
                  value={cnr}
                  onChange={(e) => setCnr(e.target.value.toUpperCase())}
                  placeholder="e.g. MHAU019999992015"
                  maxLength={16}
                  className="font-mono"
                />
                {cnr && !cnrValid && (
                  <p className="mt-1 text-xs text-gray-500">CNR must be exactly 16 letters/digits.</p>
                )}
              </div>
            </>
          ) : (
            <>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Court</label>
            <Select
              value={courtType}
              onChange={(e) => {
                setCourtType(e.target.value as CourtType);
                resetDownstream("courtType");
              }}
            >
              <option value="district">District Court</option>
              <option value="high_court">High Court</option>
            </Select>
          </div>

          {courtType === "district" ? (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">State</label>
                <Select
                  value={stateCode}
                  onChange={(e) => {
                    setStateCode(e.target.value);
                    resetDownstream("state");
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
                      resetDownstream("district");
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
                    onChange={(e) => {
                      setComplexValue(e.target.value);
                      setCaseTypeCode("");
                    }}
                    disabled={complexes.isLoading}
                  >
                    <option value="">{complexes.isLoading ? "Loading..." : "Select a court complex"}</option>
                    {renderOptions(complexes.data?.options)}
                  </Select>
                </div>
              )}
            </>
          ) : (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">High Court</label>
                <Select
                  value={hcCourtCode}
                  onChange={(e) => {
                    setHcCourtCode(e.target.value);
                    resetDownstream("hcCourt");
                  }}
                  disabled={hcCourts.isLoading}
                >
                  <option value="">{hcCourts.isLoading ? "Loading..." : "Select a High Court"}</option>
                  {renderOptions(hcCourts.data?.options)}
                </Select>
              </div>
              {hcCourtCode && (
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Bench</label>
                  <Select
                    value={benchCode}
                    onChange={(e) => {
                      setBenchCode(e.target.value);
                      setCaseTypeCode("");
                    }}
                    disabled={benches.isLoading}
                  >
                    <option value="">{benches.isLoading ? "Loading..." : "Select a bench"}</option>
                    {renderOptions(benches.data?.options)}
                  </Select>
                </div>
              )}
            </>
          )}

          {((courtType === "district" && complexOption) || (courtType === "high_court" && benchCode)) && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Case Type</label>
              <Select
                value={caseTypeCode}
                onChange={(e) => setCaseTypeCode(e.target.value)}
                disabled={caseTypes.isLoading}
              >
                <option value="">{caseTypes.isLoading ? "Loading..." : "Select a case type"}</option>
                {renderOptions(caseTypes.data?.options)}
              </Select>
            </div>
          )}

          <div className="grid grid-cols-1 @sm:grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Case Number</label>
              <Input value={caseNumber} onChange={(e) => setCaseNumber(e.target.value)} placeholder="e.g. 300" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Year</label>
              <Input value={year} onChange={(e) => setYear(e.target.value)} placeholder="e.g. 2024" />
            </div>
          </div>
            </>
          )}

          {formError && (
            <div className="flex items-start gap-2 rounded-lg bg-[#fdecec] p-3 text-sm text-[#b32e26]">
              <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
              <span>{formError}</span>
            </div>
          )}

          <Button type="submit" disabled={!canSubmit || previewTracking.isPending} className="w-full">
            {previewTracking.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Fetching from eCourts...
              </>
            ) : (
              <>
                <Search className="h-4 w-4" />
                Preview Case
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Preview / confirm step -- shows the fetched case before anything is
// persisted, so a mismatched case_type/case_number/CNR lookup can be caught
// by a human before it silently overwrites the case's tracking data.
// ---------------------------------------------------------------------------

function TrackingPreviewPanel({
  preview,
  onConfirm,
  onTryAgain,
  isConfirming,
  error,
}: {
  preview: TrackingPreview;
  onConfirm: () => void;
  onTryAgain: () => void;
  isConfirming: boolean;
  error: string | null;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Gavel className="h-5 w-5 text-gray-500" />
          Is this your case?
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="mb-4 flex items-start gap-2 rounded-lg bg-[#fdf3e0] border border-[#f5e3c2] p-3 text-xs text-[#92610f]">
          <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
          <span>
            This is fetched from eCourts and has NOT been saved yet. Check the parties below match
            before confirming.
          </span>
        </div>

        <div className="grid grid-cols-1 @sm:grid-cols-2 gap-4 mb-4">
          <Field label="Case Title">
            <span className="text-sm font-medium text-gray-900">{preview.case_title || "—"}</span>
          </Field>
          <Field label="CNR">
            <span className="font-mono text-sm">{preview.cnr || "—"}</span>
          </Field>
          <Field label="Petitioner">
            <span className="text-sm text-gray-900">{preview.petitioner || "—"}</span>
          </Field>
          <Field label="Respondent">
            <span className="text-sm text-gray-900">{preview.respondent || "—"}</span>
          </Field>
          <Field label="Court">
            <span className="text-sm text-gray-900">{preview.court_name || "—"}</span>
          </Field>
          <Field label="Next Hearing">
            <span className="text-sm text-gray-900">
              {preview.next_hearing_date ? formatDate(preview.next_hearing_date) : "None scheduled"}
            </span>
          </Field>
        </div>

        {error && (
          <div className="mb-4 flex items-start gap-2 rounded-lg bg-[#fdecec] p-3 text-sm text-[#b32e26]">
            <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex gap-3">
          <Button variant="secondary" onClick={onTryAgain} disabled={isConfirming} className="flex-1">
            Try Again
          </Button>
          <Button onClick={onConfirm} disabled={isConfirming} className="flex-1">
            {isConfirming ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Confirming...
              </>
            ) : (
              "Confirm, this is correct"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Configured display
// ---------------------------------------------------------------------------

const RATE_LIMIT_MS = 60 * 60 * 1000;

function TrackingDisplay({ caseItem, hearings }: { caseItem: Case; hearings: Hearing[] }) {
  const refreshTracking = useRefreshTracking(caseItem.id);
  const untrackTracking = useUntrackTracking(caseItem.id);
  const [rateLimitedUntil, setRateLimitedUntil] = useState<string | null>(null);
  const [hearingHistoryOpen, setHearingHistoryOpen] = useState(false);

  const ecourtsHearings = useMemo(
    () => hearings.filter((h) => h.source === "ecourts").sort((a, b) => a.hearing_date.localeCompare(b.hearing_date)),
    [hearings],
  );
  const today = new Date().toISOString().slice(0, 10);
  const nextHearing = ecourtsHearings.find((h) => h.hearing_date.slice(0, 10) >= today);

  const withinRateLimitWindow =
    caseItem.last_fetched_at &&
    Date.now() - new Date(caseItem.last_fetched_at).getTime() < RATE_LIMIT_MS;

  const portalUrl = caseItem.court_type === "high_court" ? HC_PORTAL_URL : DISTRICT_PORTAL_URL;

  async function handleRefresh() {
    try {
      const result = await refreshTracking.mutateAsync(false);
      if (result.rate_limited) {
        setRateLimitedUntil(result.retry_after || null);
        showToast.error(
          "Refresh limited",
          "This case was checked recently. Try again in a bit.",
        );
      } else {
        showToast.success(
          "Tracking refreshed",
          result.new_hearing_dates && result.new_hearing_dates.length > 0
            ? `${result.new_hearing_dates.length} new hearing date(s) found.`
            : "No changes since last check.",
        );
      }
    } catch (error) {
      showToast.error("Refresh failed", "Could not reach the court portal. Please try again later.");
    }
  }

  async function handleUntrack() {
    const confirmed = window.confirm(
      "Remove court tracking for this case? This clears the CNR, tracking configuration, and " +
        "all eCourts-sourced hearing dates (manually-entered hearings are kept). You can set up " +
        "tracking again immediately afterward with the correct case. This cannot be undone.",
    );
    if (!confirmed) return;

    try {
      await untrackTracking.mutateAsync();
      showToast.success("Tracking removed", "You can set up tracking again with the correct case.");
    } catch (error) {
      showToast.error("Could not remove tracking", "Please try again.");
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle className="flex items-center gap-2">
          <Gavel className="h-5 w-5 text-gray-500" />
          Court Tracking
        </CardTitle>
        <div className="flex items-center gap-2">
          <div title={withinRateLimitWindow ? "You can refresh again about an hour after the last check." : undefined}>
            <Button
              variant="secondary"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshTracking.isPending || !!withinRateLimitWindow}
            >
              {refreshTracking.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              {refreshTracking.isPending ? "Refreshing..." : "Refresh"}
            </Button>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleUntrack}
            disabled={untrackTracking.isPending}
            title="Untrack this case / fix a wrong case match"
            className="text-destructive hover:bg-[#fdecec] hover:text-destructive-hover"
          >
            {untrackTracking.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Untrack
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-4 rounded-lg bg-[#ebf3fb] border border-[#d6e7f7] p-3 text-xs text-[#2f6fb0]">
          Data sourced from eCourts ({caseItem.court_type === "high_court" ? "hcservices" : "services"}
          .ecourts.gov.in). May be delayed or incomplete -- always verify against official court
          records.{" "}
          <a
            href={portalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-medium underline"
          >
            Verify on eCourts <ExternalLink className="h-3 w-3" />
          </a>
        </div>

        <div className="grid grid-cols-1 @md:grid-cols-2 @3xl:grid-cols-3 gap-4 mb-4">
          <Field label="CNR">
            <span className="font-mono text-sm">{caseItem.cnr_number || "—"}</span>
          </Field>
          <Field label="Status">
            {caseItem.fetch_status === "failed" ? (
              <Badge variant="danger">Last fetch failed</Badge>
            ) : (
              <span className="text-sm text-gray-900">{nextHearing ? "Pending" : "—"}</span>
            )}
          </Field>
          <Field label="Next Hearing">
            {nextHearing ? (
              <span className="flex items-center gap-1 text-sm font-medium text-gray-900">
                <CalendarClock className="h-3.5 w-3.5 text-primary" />
                {formatDate(nextHearing.hearing_date)}
              </span>
            ) : (
              <span className="text-sm text-gray-500">None scheduled</span>
            )}
          </Field>
          <Field label="Judge">
            <span className="text-sm text-gray-900">{nextHearing?.judge || "—"}</span>
          </Field>
          <Field label="Stage / Purpose">
            <span className="text-sm text-gray-900">{nextHearing?.purpose || "—"}</span>
          </Field>
          <Field label="Last Refreshed">
            <span className="text-sm text-gray-500">
              {caseItem.last_fetched_at ? formatRelativeTime(caseItem.last_fetched_at) : "Never"}
            </span>
          </Field>
        </div>

        {ecourtsHearings.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <h4 className="text-[13px] font-semibold text-gray-700">
                Hearing History ({ecourtsHearings.length})
              </h4>
              <CollapseToggle
                isOpen={hearingHistoryOpen}
                onToggle={() => setHearingHistoryOpen((v) => !v)}
              />
            </div>
            <Collapsible isOpen={hearingHistoryOpen}>
              <div className="overflow-x-auto rounded-lg border border-gray-100">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-left text-xs text-gray-500">
                    <tr>
                      <th className="px-3 py-2 font-medium">Date</th>
                      <th className="px-3 py-2 font-medium">Purpose</th>
                      <th className="px-3 py-2 font-medium">Judge</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {[...ecourtsHearings].reverse().map((h) => (
                      <tr key={h.id} className={h.hearing_date.slice(0, 10) >= today ? "bg-[#ebf3fb]/50" : ""}>
                        <td className="px-3 py-2 whitespace-nowrap">{formatDate(h.hearing_date)}</td>
                        <td className="px-3 py-2 text-gray-600">{h.purpose || "—"}</td>
                        <td className="px-3 py-2 text-gray-600">{h.judge || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Collapsible>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs text-gray-500 mb-0.5">{label}</div>
      {children}
    </div>
  );
}
