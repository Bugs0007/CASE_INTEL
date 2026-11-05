"use client";

import { useState } from "react";
import { CalendarClock, ClipboardCheck, ClipboardList, MapPin, User } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CauseListBadge, CauseListInfo } from "@/components/hearings/cause-list-badge";
import { HearingDigestDialog } from "@/components/hearings/hearing-digest-dialog";
import { hearingDayKey } from "@/lib/calendar";
import { nextHearing } from "@/lib/case-previews";
import { daysUntilDate } from "@/lib/tasks";
import { formatHearingDate } from "@/lib/utils";
import type { Hearing } from "@/types";

function untilLabel(days: number): string {
  if (days <= 0) return "Today";
  if (days === 1) return "Tomorrow";
  return `In ${days} days`;
}

/** The next court date, at the top of the side rail: when, where, and the
 * hearing prep sheet. */
export function NextHearingCard({ hearings }: { hearings: Hearing[] }) {
  const hearing = nextHearing(hearings);
  const [prepId, setPrepId] = useState<number | null>(null);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4" />
          Next hearing
        </CardTitle>
      </CardHeader>
      <CardContent>
        {hearing ? (
          <div className="space-y-2">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
              <span className="text-lg font-semibold font-mono text-gray-900">
                {formatHearingDate(hearing.hearing_date)}
              </span>
              <span className="ci-chip ci-chip--pending">
                {untilLabel(daysUntilDate(hearingDayKey(hearing.hearing_date)))}
              </span>
              <span className="ci-chip ci-chip--none">{hearing.hearing_type_display}</span>
            </div>
            <div className="space-y-1 text-sm text-gray-600">
              {hearing.location && (
                <div className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 flex-shrink-0" />
                  <span>{hearing.location}</span>
                </div>
              )}
              {hearing.judge && (
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4 flex-shrink-0" />
                  <span>{hearing.judge}</span>
                </div>
              )}
              {hearing.purpose && (
                <div className="flex items-center gap-2">
                  <ClipboardList className="h-4 w-4 flex-shrink-0" />
                  <span>{hearing.purpose}</span>
                </div>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <CauseListBadge hearing={hearing} />
            </div>
            <CauseListInfo hearing={hearing} />
            <Button variant="secondary" size="sm" onClick={() => setPrepId(hearing.id)}>
              <ClipboardCheck className="h-4 w-4 mr-1" />
              Prep sheet
            </Button>
          </div>
        ) : (
          <p className="text-sm text-gray-500">No upcoming hearing is scheduled.</p>
        )}
      </CardContent>
      <HearingDigestDialog hearingId={prepId} onClose={() => setPrepId(null)} />
    </Card>
  );
}
