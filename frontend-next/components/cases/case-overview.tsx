import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import type { Case } from "@/types";

interface CaseOverviewProps {
  case: Case;
}

export function CaseOverview({ case: caseItem }: CaseOverviewProps) {
  const overviewFields = [
    { label: "Plaintiff/Client", value: caseItem.client_name },
    {
      label: "Defendant/Opposing Party",
      value: caseItem.opposing_party || "N/A",
    },
    { label: "Practice Area", value: caseItem.case_type || "N/A" },
    { label: "Case Status", value: caseItem.status },
    { label: "Priority", value: caseItem.priority },
    { label: "Filing Date", value: caseItem.filing_date || "N/A" },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Case Overview</CardTitle>
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
