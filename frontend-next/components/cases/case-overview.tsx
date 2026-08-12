"use client";

import { useState } from "react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CaseDetailsDialog } from "@/components/cases/case-details-dialog";
import { Pencil } from "lucide-react";
import { primaryClientContact } from "@/lib/utils";
import type { Case, UserPartyRole } from "@/types";

interface CaseOverviewProps {
  case: Case;
}

const PARTY_ROLE_LABELS: Record<UserPartyRole, string> = {
  unknown: "Unknown",
  petitioner: "Petitioner",
  respondent: "Respondent",
};

export function CaseOverview({ case: caseItem }: CaseOverviewProps) {
  const [isEditOpen, setIsEditOpen] = useState(false);
  const client = primaryClientContact(caseItem.client_contacts);

  const overviewFields = [
    { label: "Plaintiff/Client", value: client?.name || "No client on file" },
    {
      label: "Defendant/Opposing Party",
      value: caseItem.opposing_party || "N/A",
    },
    { label: "Your Client's Side", value: PARTY_ROLE_LABELS[caseItem.user_party_role] },
    { label: "Practice Area", value: caseItem.case_type || "N/A" },
    { label: "Case Status", value: caseItem.status },
    { label: "Priority", value: caseItem.priority },
    { label: "Filing Date", value: caseItem.filing_date || "N/A" },
  ];

  return (
    <Card>
      <CardHeader className="flex items-center justify-between">
        <CardTitle>Case Overview</CardTitle>
        <Button variant="secondary" size="sm" onClick={() => setIsEditOpen(true)}>
          <Pencil className="h-3.5 w-3.5" />
          Edit Details
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 @sm:grid-cols-2 gap-4">
          {overviewFields.map((field) => (
            <div key={field.label} className="space-y-1">
              <dt className="text-xs text-gray-400 mb-1">
                {field.label}
              </dt>
              <dd className="text-sm text-gray-900 font-medium">
                {field.value}
              </dd>
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
                {caseItem.client_contacts.map((contact) => (
                  <li key={contact.id} className="text-sm text-gray-700 flex items-center gap-2">
                    <span className="font-medium text-gray-900">{contact.name}</span>
                    <span className="text-xs text-gray-400 capitalize">{contact.role}</span>
                    {contact.is_billing_contact && (
                      <span className="ci-chip ci-chip--none">
                        Billing
                      </span>
                    )}
                    {(contact.email || contact.phone) && (
                      <span className="text-xs text-gray-400">
                        {[contact.email, contact.phone].filter(Boolean).join(" · ")}
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

      <CaseDetailsDialog
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        case={caseItem}
      />
    </Card>
  );
}
