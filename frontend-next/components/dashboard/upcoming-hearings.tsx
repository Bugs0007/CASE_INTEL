import Link from "next/link";
import { CalendarClock, Gavel } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn, formatDate } from "@/lib/utils";
import type { UpcomingHearing } from "@/types";

interface UpcomingHearingsProps {
  hearings: UpcomingHearing[];
}

function urgencyClasses(daysUntil: number): { row: string; badge: string } {
  if (daysUntil <= 7) {
    return { row: "border-red-100 bg-red-50/50", badge: "bg-red-100 text-red-700" };
  }
  if (daysUntil <= 30) {
    return { row: "border-amber-100 bg-amber-50/50", badge: "bg-amber-100 text-amber-700" };
  }
  return { row: "border-gray-100", badge: "bg-gray-100 text-gray-600" };
}

export function UpcomingHearings({ hearings }: UpcomingHearingsProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-5 w-5 text-gray-500" />
          Upcoming Hearings
        </CardTitle>
      </CardHeader>
      <CardContent>
        {hearings.length === 0 ? (
          <div className="text-center py-8">
            <Gavel className="h-10 w-10 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-500 text-sm">No upcoming hearings</p>
          </div>
        ) : (
          <div className="space-y-2">
            {hearings.map((hearing) => {
              const { row, badge } = urgencyClasses(hearing.days_until);
              return (
                <Link
                  key={hearing.id}
                  href={`/cases/${hearing.case_id}`}
                  className={cn(
                    "flex items-center justify-between rounded-lg border p-3 transition-colors hover:bg-gray-50",
                    row,
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-medium text-gray-900 truncate">{hearing.case_title}</div>
                    <div className="text-xs text-gray-500">
                      {hearing.case_number}
                      {hearing.purpose && <> • {hearing.purpose}</>}
                    </div>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-3 ml-4">
                    <span className="text-sm text-gray-600">{formatDate(hearing.hearing_date)}</span>
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", badge)}>
                      {hearing.days_until === 0
                        ? "Today"
                        : hearing.days_until === 1
                          ? "Tomorrow"
                          : `${hearing.days_until} days`}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
