import Link from "next/link";
import { format, parseISO } from "date-fns";
import { Landmark } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Hearing } from "@/types";

interface CalendarByCourtProps {
  hearings: Hearing[];
  caseMeta: Map<number, { caseNumber: string; documentCount: number }>;
}

export function CalendarByCourt({ hearings, caseMeta }: CalendarByCourtProps) {
  const byCourt = new Map<string, Hearing[]>();
  for (const h of hearings) {
    const court = h.location?.trim() || "No location specified";
    const list = byCourt.get(court) ?? [];
    list.push(h);
    byCourt.set(court, list);
  }

  const groups = Array.from(byCourt.entries())
    .map(([court, courtHearings]) => {
      const sorted = courtHearings
        .slice()
        .sort((a, b) => a.hearing_date.localeCompare(b.hearing_date));
      return { court, hearings: sorted, earliest: sorted[0].hearing_date };
    })
    .sort((a, b) => a.earliest.localeCompare(b.earliest));

  if (groups.length === 0) {
    return (
      <div className="bg-white border border-gray-100 rounded-xl shadow-sm p-10 text-center text-sm text-gray-500">
        No upcoming hearings to group by court.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {groups.map((g) => (
        <div key={g.court} className="bg-white border border-gray-100 rounded-xl shadow-sm">
          <div className="px-5 py-3.5 border-b border-gray-100 flex items-center gap-2.5">
            <Landmark className="h-4 w-4 text-gray-500 flex-shrink-0" />
            <div className="text-[15px] font-bold text-gray-900">{g.court}</div>
            <span className="inline-flex items-center h-5 px-2 rounded-full bg-gray-100 text-gray-600 text-[11px] font-bold">
              {g.hearings.length} hearing{g.hearings.length === 1 ? "" : "s"}
            </span>
          </div>
          <div className="px-5 py-2">
            {g.hearings.map((h) => {
              const meta = caseMeta.get(h.case);
              return (
                <div
                  key={h.id}
                  className="flex items-center justify-between gap-3 py-3 border-b border-gray-50 last:border-b-0 flex-wrap"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-[70px] flex-shrink-0 text-[13px] font-bold text-gray-900">
                      {format(parseISO(h.hearing_date), "MMM d")}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 mb-0.5 flex-wrap">
                        <span className="text-sm font-semibold text-gray-900">
                          {h.case_title}
                        </span>
                        <span
                          className={cn(
                            "inline-flex items-center h-[18px] px-1.5 rounded-full text-[10.5px] font-bold",
                            h.source === "ecourts"
                              ? "bg-[#ebf3fb] text-[#2f6fb0]"
                              : "bg-gray-100 text-gray-600",
                          )}
                        >
                          {h.source === "ecourts" ? "eCourts" : "Manual"}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500">
                        {format(parseISO(h.hearing_date), "h:mm a")}
                        {meta ? ` · ${meta.documentCount} docs on file` : ""}
                      </div>
                    </div>
                  </div>
                  <Link href={`/cases/${h.case}`}>
                    <Button variant="secondary" size="sm">
                      View Case
                    </Button>
                  </Link>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
