import Link from "next/link";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { reasonForCase, sortByUrgencyPriority } from "@/lib/case-urgency";
import { staggerDelay } from "@/lib/utils";
import type { Case } from "@/types";

interface CasesByUrgencyProps {
  /** All cases (needs_attention already computed server-side per case). */
  cases: Case[];
  /** Case IDs with a hearing within the next 7 days. */
  hearingSoonCaseIds: Set<number>;
  /** Case IDs with an eCourts hearing update since the user's last visit. */
  ecourtsUpdateCaseIds: Set<number>;
  /** Case IDs with at least one failed document. */
  failedDocCaseIds: Set<number>;
}

export function CasesByUrgency({
  cases,
  hearingSoonCaseIds,
  ecourtsUpdateCaseIds,
  failedDocCaseIds,
}: CasesByUrgencyProps) {
  const needsAttention = sortByUrgencyPriority(cases.filter((c) => c.needs_attention));
  const otherCount = cases.length - needsAttention.length;

  return (
    <Card className="mb-5">
      <CardHeader>
        <CardTitle>Cases</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-eyebrow text-[#9a4a12] mb-3">
          Needs Attention This Week · {needsAttention.length}
        </div>
        {needsAttention.length === 0 ? (
          <p className="text-sm text-gray-500 py-2">
            No cases need attention this week.
          </p>
        ) : (
          <div className="space-y-2">
            {needsAttention.map((c, i) => {
              const reason = reasonForCase(
                c.id,
                hearingSoonCaseIds,
                ecourtsUpdateCaseIds,
                failedDocCaseIds,
              );
              return (
                <div
                  key={c.id}
                  style={staggerDelay(i)}
                  className="flex items-center justify-between gap-3 p-3 border border-gray-100 rounded-lg flex-wrap animate-fade-up motion-reduce:animate-none"
                >
                  <div className="min-w-0 flex items-center gap-3 flex-wrap">
                    <span
                      className={`inline-flex items-center h-5 px-2 rounded-full text-[11px] font-semibold flex-shrink-0 ${reason.className}`}
                    >
                      {reason.label}
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-gray-900">
                        {c.title}
                      </div>
                      <div className="text-xs text-gray-500">
                        {c.case_number} · {c.priority} priority
                      </div>
                    </div>
                  </div>
                  <Link href={`/cases/${c.id}`}>
                    <Button variant="secondary" size="sm">
                      View Case
                    </Button>
                  </Link>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
      <CardFooter className="flex items-center justify-between flex-wrap gap-2">
        <div className="text-sm text-gray-600">
          <span className="font-semibold text-gray-900">
            {otherCount} other case{otherCount === 1 ? "" : "s"}
          </span>{" "}
          with nothing due this week
        </div>
        <Link href="/cases" className="text-sm font-semibold text-primary hover:underline">
          View All Cases →
        </Link>
      </CardFooter>
    </Card>
  );
}
