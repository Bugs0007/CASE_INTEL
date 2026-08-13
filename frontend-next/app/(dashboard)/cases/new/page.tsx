"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, FileEdit, Search } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { showToast } from "@/components/ui/toaster";
import { useCreateCase } from "@/hooks/use-cases";
import { APIError } from "@/lib/api/client";
import type {
  CaseCreateInput,
  CasePriority,
  CaseStatus,
  CaseType,
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
  const createCase = useCreateCase();

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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    if (!canSubmit) return;

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
      if (error instanceof APIError && error.data && typeof error.data === "object") {
        const payloadErr = error.data as Record<string, unknown>;
        const firstField = Object.keys(payloadErr)[0];
        const detail =
          firstField && Array.isArray(payloadErr[firstField]) && payloadErr[firstField][0]
            ? String(payloadErr[firstField][0])
            : "Could not add the case. Please check the fields and try again.";
        setFormError(detail);
      } else {
        setFormError("Could not reach the server. Please try again.");
      }
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
                <span>{formError}</span>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Button type="submit" disabled={!canSubmit || createCase.isPending}>
                {createCase.isPending ? "Adding Case…" : "Add Case"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
