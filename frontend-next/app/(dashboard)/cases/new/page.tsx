"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, FileEdit, Gavel, Loader2, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import { useCreateCase } from "@/hooks/use-cases";
import { useCnrLookup, useCreateCaseFromCnr } from "@/hooks/use-case-tracking";
import { APIError } from "@/lib/api/client";
import type {
  CaseCreateInput,
  CasePriority,
  CaseStatus,
  CaseType,
  CnrLookupPreview,
  UserPartyRole,
} from "@/types";

const CASE_TYPES: { value: CaseType; label: string }[] = [
  { value: "civil", label: "Civil" },
  { value: "criminal", label: "Criminal" },
  { value: "family", label: "Family" },
  { value: "corporate", label: "Corporate" },
  { value: "ip", label: "Intellectual Property" },
  { value: "labor", label: "Labor" },
  { value: "tax", label: "Tax" },
  { value: "other", label: "Other" },
];

const STATUSES: { value: CaseStatus; label: string }[] = [
  { value: "open", label: "Open" },
  { value: "pending", label: "Pending" },
  { value: "closed", label: "Closed" },
  { value: "archived", label: "Archived" },
];

const PRIORITIES: { value: CasePriority; label: string }[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "critical", label: "Critical" },
];

const PARTY_ROLES: { value: UserPartyRole; label: string }[] = [
  { value: "unknown", label: "Unknown" },
  { value: "petitioner", label: "Petitioner" },
  { value: "respondent", label: "Respondent" },
];

export default function NewCasePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const createCase = useCreateCase();
  const cnrLookup = useCnrLookup();
  const createCaseFromCnr = useCreateCaseFromCnr();

  // ?mode=cnr lands directly in the Track-by-CNR toggle state -- the New
  // Case chooser (components/cases/new-case-chooser-dialog.tsx) links
  // here with it so picking "Track by CNR" doesn't dump the advocate on
  // the manual form with one more click to make. Read once at mount;
  // the toggle buttons take over from here (no need to keep syncing the
  // URL as the user clicks between modes).
  const [mode, setMode] = useState<"manual" | "cnr">(() =>
    searchParams.get("mode") === "cnr" ? "cnr" : "manual",
  );
  const [cnr, setCnr] = useState("");
  const [cnrError, setCnrError] = useState<string | null>(null);
  const [preview, setPreview] = useState<CnrLookupPreview | null>(null);
  const [duplicateCase, setDuplicateCase] = useState<{ id: number; case_number: string } | null>(
    null,
  );

  const [caseNumber, setCaseNumber] = useState("");
  const [title, setTitle] = useState("");
  const [opposingParty, setOpposingParty] = useState("");
  const [userPartyRole, setUserPartyRole] = useState<UserPartyRole>("unknown");
  const [caseType, setCaseType] = useState<CaseType | "">("");
  const [status, setStatus] = useState<CaseStatus>("open");
  const [priority, setPriority] = useState<CasePriority>("medium");
  const [filingDate, setFilingDate] = useState("");
  const [notes, setNotes] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const canSubmit = caseNumber.trim().length > 0 && title.trim().length > 0;
  const cnrValid = cnr.trim().length === 16 && /^[a-zA-Z0-9]+$/.test(cnr.trim());

  function switchMode(next: "manual" | "cnr") {
    setMode(next);
    setPreview(null);
    setCnrError(null);
    setDuplicateCase(null);
  }

  function extractErrorDetail(error: unknown): {
    detail: string;
    duplicate: { id: number; case_number: string } | null;
  } {
    if (error instanceof APIError && error.data && typeof error.data === "object") {
      const data = error.data as Record<string, unknown>;
      if (data.code === "duplicate_cnr" && typeof data.case_id === "number") {
        return {
          detail: String(data.detail || "You're already tracking this CNR."),
          duplicate: { id: data.case_id, case_number: String(data.case_number ?? "") },
        };
      }
      if (typeof data.detail === "string") {
        return { detail: data.detail, duplicate: null };
      }
      const firstField = Object.keys(data)[0];
      const detail =
        firstField && Array.isArray(data[firstField]) && data[firstField][0]
          ? String(data[firstField][0])
          : "Something went wrong. Please try again.";
      return { detail, duplicate: null };
    }
    return { detail: "Could not reach the server. Please try again.", duplicate: null };
  }

  async function handleCnrFetch(e: React.FormEvent) {
    e.preventDefault();
    setCnrError(null);
    setDuplicateCase(null);
    if (!cnrValid) return;

    try {
      const result = await cnrLookup.mutateAsync({ cnr: cnr.trim().toUpperCase() });
      setPreview(result);
      setCaseNumber(result.case_number);
      setTitle(result.title);
      setUserPartyRole(result.user_party_role);
      setOpposingParty(result.opposing_party || "");
    } catch (error) {
      const { detail, duplicate } = extractErrorDetail(error);
      setCnrError(detail);
      setDuplicateCase(duplicate);
    }
  }

  function handleUseDifferentCnr() {
    setPreview(null);
    setCnrError(null);
    setDuplicateCase(null);
    setCaseNumber("");
    setTitle("");
    setOpposingParty("");
    setUserPartyRole("unknown");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    setDuplicateCase(null);
    if (!canSubmit) return;

    if (mode === "cnr" && preview) {
      try {
        const created = await createCaseFromCnr.mutateAsync({
          preview_token: preview.preview_token,
          case_number: caseNumber.trim(),
          title: title.trim(),
          opposing_party: opposingParty.trim() || undefined,
          user_party_role: userPartyRole,
          case_type: caseType || undefined,
          status,
          priority,
          filing_date: filingDate || undefined,
          notes: notes.trim() || undefined,
        });
        showToast.success("Case added", "Fetched from eCourts and tracking is already set up.");
        router.push(`/cases/${created.id}`);
      } catch (error) {
        const { detail, duplicate } = extractErrorDetail(error);
        setFormError(detail);
        setDuplicateCase(duplicate);
        if (error instanceof APIError && error.status === 410) {
          // Stale preview_token -- send the advocate back to the CNR step
          // rather than leaving them stuck resubmitting a dead token.
          setPreview(null);
        }
      }
      return;
    }

    const payload: CaseCreateInput = {
      case_number: caseNumber.trim(),
      title: title.trim(),
      opposing_party: opposingParty.trim() || undefined,
      user_party_role: userPartyRole,
      case_type: caseType || undefined,
      status,
      priority,
      filing_date: filingDate || undefined,
      notes: notes.trim() || undefined,
    };

    try {
      const created = await createCase.mutateAsync(payload);
      showToast.success(
        "Case added",
        "Add client contacts and set up court tracking from the case page whenever you're ready.",
      );
      router.push(`/cases/${created.id}`);
    } catch (error) {
      const { detail, duplicate } = extractErrorDetail(error);
      setFormError(detail);
      setDuplicateCase(duplicate);
    }
  }

  return (
    <div className="px-4 sm:px-7 pt-5 sm:pt-7 pb-[60px] max-w-[700px] mx-auto">
      <div className="mb-5">
        <Link
          href="/cases"
          className="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Cases
        </Link>
        <h1 className="text-page-title text-gray-900 mt-2 mb-1.5">Add a Case Manually</h1>
        <p className="text-sm text-gray-600">
          Type in the case details yourself instead of searching eCourts — useful for a case
          that hasn&apos;t shown up in a search yet, or one you&apos;d just rather enter by hand.
          You can add client contacts and link this case to its eCourts record (by CNR) from the
          case page any time after it&apos;s created.
        </p>
        <Link
          href="/cases/search"
          className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline mt-2"
        >
          <Search className="h-3.5 w-3.5" />
          Prefer to search by advocate name or bar code instead?
        </Link>
      </div>

      <div className="mb-4 flex gap-2 text-sm">
        <button
          type="button"
          onClick={() => switchMode("manual")}
          className={`rounded-full px-3 py-1 font-medium transition-colors ${
            mode === "manual" ? "bg-primary text-page" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          Enter Manually
        </button>
        <button
          type="button"
          onClick={() => switchMode("cnr")}
          className={`rounded-full px-3 py-1 font-medium transition-colors ${
            mode === "cnr" ? "bg-primary text-page" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
          }`}
        >
          Track by CNR
        </button>
      </div>

      {mode === "cnr" && !preview && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Gavel className="h-5 w-5 text-gray-500" />
              Track by CNR
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-gray-600 mb-4">
              Enter the case&apos;s CNR number to fetch its details from eCourts and pre-fill the
              form below — faster than typing everything by hand. You&apos;ll still get to review
              and edit before the case is created.
            </p>
            <form onSubmit={handleCnrFetch} className="space-y-4">
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
                <p className="mt-1 text-xs text-gray-500">
                  District Court vs. High Court is detected automatically from the CNR.
                </p>
              </div>

              {cnrError && (
                <div className="flex items-start gap-2 rounded-lg bg-status-alert-soft p-3 text-sm text-status-alert">
                  <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                  <div>
                    <span>{cnrError}</span>
                    {duplicateCase && (
                      <>
                        {" "}
                        <Link href={`/cases/${duplicateCase.id}`} className="font-medium underline">
                          View {duplicateCase.case_number}
                        </Link>
                      </>
                    )}
                  </div>
                </div>
              )}

              <Button type="submit" disabled={!cnrValid || cnrLookup.isPending} className="w-full">
                {cnrLookup.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Fetching from eCourts...
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" />
                    Fetch
                  </>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {mode === "cnr" && preview && (
        <div className="mb-5 rounded-lg bg-status-pending-soft border border-status-pending p-3 text-xs text-status-pending">
          <div className="mb-1 font-medium">
            Fetched from eCourts — not saved yet. Review the details below before adding the case.
          </div>
          <div>
            {preview.petitioner || "—"} vs {preview.respondent || "—"} · {preview.court_name || "—"}
            {preview.court_type_detected && (
              <span className="ml-1.5 rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-500">
                {preview.court_type === "high_court" ? "High Court" : "District Court"} detected from CNR
              </span>
            )}
          </div>
        </div>
      )}

      {(mode === "manual" || (mode === "cnr" && preview)) && (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileEdit className="h-5 w-5 text-gray-500" />
            Case Details
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Case Number <span className="text-status-alert">*</span>
                </label>
                <Input
                  value={caseNumber}
                  onChange={(e) => setCaseNumber(e.target.value)}
                  placeholder="e.g. WP/14562/2024"
                  className="font-mono"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Title <span className="text-status-alert">*</span>
                </label>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g., Ramesh Kumar vs. TSSPDCL"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Your Client&apos;s Side
                </label>
                <Select
                  value={userPartyRole}
                  onChange={(e) => setUserPartyRole(e.target.value as UserPartyRole)}
                >
                  {PARTY_ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Opposing Party <span className="font-normal text-gray-400">(optional)</span>
                </label>
                <Input
                  value={opposingParty}
                  onChange={(e) => setOpposingParty(e.target.value)}
                  placeholder="e.g., Jane Johnson"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Practice Area <span className="font-normal text-gray-400">(optional)</span>
                </label>
                <Select value={caseType} onChange={(e) => setCaseType(e.target.value as CaseType)}>
                  <option value="">Not set</option>
                  {CASE_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Status</label>
                <Select value={status} onChange={(e) => setStatus(e.target.value as CaseStatus)}>
                  {STATUSES.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Priority</label>
                <Select value={priority} onChange={(e) => setPriority(e.target.value as CasePriority)}>
                  {PRIORITIES.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </Select>
              </div>
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Filing Date <span className="font-normal text-gray-400">(optional)</span>
              </label>
              <Input type="date" value={filingDate} onChange={(e) => setFilingDate(e.target.value)} />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Notes <span className="font-normal text-gray-400">(optional)</span>
              </label>
              <Textarea
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Anything worth remembering about this case"
              />
            </div>

            {formError && (
              <div className="flex items-start gap-2 rounded-lg bg-status-alert-soft p-3 text-sm text-status-alert">
                <AlertTriangle className="h-4 w-4 flex-shrink-0 mt-0.5" />
                <div>
                  <span>{formError}</span>
                  {duplicateCase && (
                    <>
                      {" "}
                      <Link href={`/cases/${duplicateCase.id}`} className="font-medium underline">
                        View {duplicateCase.case_number}
                      </Link>
                    </>
                  )}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              {mode === "cnr" && preview && (
                <Button type="button" variant="secondary" onClick={handleUseDifferentCnr}>
                  Use a Different CNR
                </Button>
              )}
              <Button
                type="submit"
                disabled={!canSubmit || createCase.isPending || createCaseFromCnr.isPending}
              >
                {createCase.isPending || createCaseFromCnr.isPending ? "Adding Case…" : "Add Case"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      )}
    </div>
  );
}
