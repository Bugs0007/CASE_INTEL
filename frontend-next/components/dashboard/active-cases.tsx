import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PriorityBadge } from "@/components/ui/badge";
import { Eye } from "lucide-react";
import type { ActiveCaseSummary } from "@/types";

interface ActiveCasesProps {
  cases: ActiveCaseSummary[];
}

export function ActiveCases({ cases }: ActiveCasesProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Active Cases</CardTitle>
      </CardHeader>
      <CardContent>
        {cases.length === 0 ? (
          <p className="text-gray-500 text-sm py-4">No active cases</p>
        ) : (
          <div className="space-y-3">
            {cases.map((caseItem) => (
              <div
                key={caseItem.id}
                className="p-4 border border-gray-100 rounded-lg hover:border-gray-200 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <PriorityBadge priority={caseItem.priority} />
                      <span className="text-xs text-gray-500 font-mono">
                        {caseItem.case_number}
                      </span>
                    </div>
                    <h4 className="font-medium text-gray-900 mb-1 truncate">
                      {caseItem.title}
                    </h4>
                    <div className="text-xs text-gray-500">
                      {caseItem.document_count} documents
                    </div>
                  </div>
                  <Link href={`/cases/${caseItem.id}`}>
                    <Button variant="ghost" size="sm">
                      <Eye className="h-4 w-4" />
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
        {cases.length > 0 && (
          <div className="pt-4 border-t border-gray-100 mt-4">
            <Link href="/cases">
              <Button variant="secondary" size="sm" className="w-full">
                View All Cases
              </Button>
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
