"use client";

import Link from "next/link";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Pencil } from "lucide-react";
import { primaryClientContact } from "@/lib/utils";
import type { Case, UserPartyRole } from "@/types";

interface CaseOverviewProps {
  case: Case;
  /** Opens Edit Details -- the dialog lives on the page, so other cards
   * (the "add a client email" note) can open it too. */
  onEditDetails: () => void;
}

const PARTY_ROLE_LABELS: Record<UserPartyRole, string> = {
  unknown: "Unknown",
  petitioner: "Petitioner",
  respondent: "Respondent",
};

function PartyValue({ name, isOurs }: { name: string; isOurs: boolean }) {
  if (!name) return <span className="text-gray-400 font-normal">Not recorded</span>;
  return (
    <span>
      {name}
      {isOurs && <span className="ml-1.5 ci-chip ci-chip--ok align-middle">your client</span>}
    </span>
  );
}

/** Two different "client" ideas live on a case, and they are shown apart:
 *   - the PARTY you act for (petitioner or respondent, per the court
 *     record or the title), and
 *   - who you talk to and bill: the primary CONTACT (a person on this
 *     case) and the CLIENT record invoices are grouped under.
 * Mixing them made one case read "Karthik Bablu" here while Billing said
 * it had no client. */
export function CaseOverview({ case: caseItem, onEditDetails }: CaseOverviewProps) {
  const contact = primaryClientContact(caseItem.client_contacts);
  const parties = caseItem.parties;
  const role = caseItem.user_party_role;
  const petitioner = parties?.petitioner ?? "";
  const respondent = parties?.respondent ?? "";
  const opposing = caseItem.opposing_party || parties?.opposing || "";

  const overviewFields: { label: string; value: React.ReactNode; hint?: string }[] = [
    {
      label: "Petitioner",
      value: <PartyValue name={petitioner} isOurs={role === "petitioner"} />,
      hint: parties?.source === "title" ? "From the case title" : undefined,
    },
    {
      label: "Respondent",
      value: <PartyValue name={respondent} isOurs={role === "respondent"} />,
      hint: parties?.source === "title" ? "From the case title" : undefined,
    },
    { label: "Your Client's Side", value: PARTY_ROLE_LABELS[role] },
    {
      label: "Opposing Party",
      value:
        opposing ||
        (role === "unknown" ? (
          <span className="text-gray-400 font-normal">Set your client&apos;s side</span>
        ) : (
          <span className="text-gray-400 font-normal">Not recorded</span>
        )),
    },
    {
      label: "Primary Contact",
      value: contact ? (
        <span>
          {contact.name}
          {contact.email && <span className="block text-xs font-normal text-gray-500">{contact.email}</span>}
        </span>
      ) : (
        <span className="text-gray-400 font-normal">None yet</span>
      ),
    },
    {
      label: "Client (billed)",
      value: caseItem.client_detail ? (
        <Link href="/clients" className="underline decoration-gray-300 underline-offset-2">
          {caseItem.client_detail.name}
        </Link>
      ) : (
        <span className="text-gray-400 font-normal">Not linked -- set it in Edit Details</span>
      ),
    },
    { label: "Practice Area", value: caseItem.case_type || "N/A" },
    { label: "Case Status", value: caseItem.status },
    { label: "Priority", value: caseItem.priority },
    { label: "Filing Date", value: caseItem.filing_date || "N/A" },
  ];

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Case Overview</CardTitle>
        <Button variant="secondary" size="sm" onClick={onEditDetails}>
          <Pencil className="h-3.5 w-3.5" />
          Edit Details
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 @sm:grid-cols-2 gap-4">
          {overviewFields.map((field) => (
            <div key={field.label} className="space-y-1 min-w-0">
              <dt className="text-xs text-gray-400 mb-1">
                {field.label}
                {field.hint && <span className="ml-1 text-gray-400">· {field.hint}</span>}
              </dt>
              <dd className="text-sm text-gray-900 font-medium break-words">{field.value}</dd>
            </div>
          ))}
        </div>

        {caseItem.client_contacts.length > 1 && (
          <div className="mt-2 pt-4 border-t border-gray-100">
            <dt className="text-sm font-medium text-gray-500 mb-2">
              Client Contacts
            </dt>
            <dd>
              <ul className="space-y-1.5">
                {caseItem.client_contacts.map((c) => (
                  <li key={c.id} className="text-sm text-gray-700 flex flex-wrap items-center gap-2">
                    <span className="font-medium text-gray-900">{c.name}</span>
                    <span className="text-xs text-gray-400 capitalize">{c.role}</span>
                    {c.is_billing_contact && (
                      <span className="ci-chip ci-chip--none">
                        Billing
                      </span>
                    )}
                    {(c.email || c.phone) && (
                      <span className="text-xs text-gray-400">
                        {[c.email, c.phone].filter(Boolean).join(" · ")}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        )}

        {caseItem.notes && (
          <div className="mt-6 pt-6 border-t border-gray-100">
            <dt className="text-sm font-medium text-gray-500 mb-2">
              Description
            </dt>
            <dd className="text-sm text-gray-700 whitespace-pre-wrap">
              {caseItem.notes}
            </dd>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
