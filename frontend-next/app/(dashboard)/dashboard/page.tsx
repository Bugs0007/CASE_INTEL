"use client";

import { useEffect, useMemo, useState } from "react";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { NeedsAttention } from "@/components/dashboard/needs-attention";
import { HearingDensityStrip } from "@/components/dashboard/hearing-density-strip";
import { CasesByUrgency } from "@/components/dashboard/cases-by-urgency";
import { DueSoon } from "@/components/dashboard/due-soon";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { RefreshAllButton } from "@/components/dashboard/refresh-all-button";
import { useDashboard, useUpcomingHearings } from "@/hooks/use-dashboard";
import { useDocuments } from "@/hooks/use-documents";
import { useCases } from "@/hooks/use-cases";
import { useTasks } from "@/hooks/use-tasks";
import { daysUntilDate, localIsoDate } from "@/lib/tasks";
import { getLastDashboardVisit, setLastDashboardVisit } from "@/lib/last-visit";

// How far ahead the Due Soon card looks (overdue tasks always included).
const DUE_SOON_DAYS = 14;

export default function DashboardPage() {
  const { data: dashboardData, isLoading, error } = useDashboard();

  // Capture the previous visit's timestamp before overwriting it, so
  // "changed since last login" queries have something to compare against.
  const [since, setSince] = useState<string | undefined>(undefined);
  useEffect(() => {
    const previous = getLastDashboardVisit();
    setSince(previous ?? undefined);
    setLastDashboardVisit(new Date().toISOString());
  }, []);

  const { data: upcomingHearings = [] } = useUpcomingHearings();
  const { data: ecourtsUpdates = [] } = useUpcomingHearings(since);
  const { data: failedDocuments = [] } = useDocuments({
    processing_status: "failed",
  });
  const { data: cases = [] } = useCases("all", since);
  // Open tasks due up to the window's end -- includes everything overdue.
  const [dueSoonCutoff] = useState(() => localIsoDate(DUE_SOON_DAYS));
  const { data: dueSoonTasks = [] } = useTasks({ status: "open", due_before: dueSoonCutoff });
  const overdueTasks = useMemo(
    () => dueSoonTasks.filter((t) => t.due_date && daysUntilDate(t.due_date) < 0),
    [dueSoonTasks],
  );

  const hearingsSoon = useMemo(
    () => upcomingHearings.filter((h) => h.days_until <= 1),
    [upcomingHearings],
  );
  const hearingSoonCaseIds = useMemo(
    () => new Set(upcomingHearings.filter((h) => h.days_until <= 7).map((h) => h.case_id)),
    [upcomingHearings],
  );
  const ecourtsUpdateCaseIds = useMemo(
    () => new Set(ecourtsUpdates.map((h) => h.case_id)),
    [ecourtsUpdates],
  );
  const failedDocCaseIds = useMemo(
    () =>
      new Set(
        failedDocuments
          .filter((d): d is typeof d & { case_id: number } => d.case_id != null)
          .map((d) => d.case_id),
      ),
    [failedDocuments],
  );

  if (isLoading) {
    return <DashboardSkeleton />;
  }

  if (error) {
    return (
      <div className="px-4 sm:px-7 pt-5 sm:pt-7">
        <div className="text-center py-12">
          <div className="text-status-alert text-lg font-medium mb-2">
            Failed to load dashboard
          </div>
          <div className="text-gray-500 text-sm">
            Please try refreshing the page
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="px-4 sm:px-7 pt-5 sm:pt-7 pb-[60px] max-w-[1240px] mx-auto">
      {/* Refresh every tracked case from eCourts (background job) */}
      <RefreshAllButton />

      {/* Needs Your Attention */}
      <NeedsAttention
        hearingsSoon={hearingsSoon}
        ecourtsUpdates={ecourtsUpdates}
        failedDocuments={failedDocuments}
        overdueTasks={overdueTasks}
      />

      {/* Next 14 Days density strip */}
      <HearingDensityStrip hearings={upcomingHearings} />

      {/* Tasks and deadlines due soon, across every case */}
      <DueSoon tasks={dueSoonTasks} windowDays={DUE_SOON_DAYS} />

      {/* Cases grouped by urgency */}
      <CasesByUrgency
        cases={cases}
        hearingSoonCaseIds={hearingSoonCaseIds}
        ecourtsUpdateCaseIds={ecourtsUpdateCaseIds}
        failedDocCaseIds={failedDocCaseIds}
      />

      {/* Recent Activity */}
      <RecentActivity activities={dashboardData?.recent_activity || []} />
    </div>
  );
}
