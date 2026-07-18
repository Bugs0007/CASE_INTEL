"use client";

import { useEffect, useMemo, useState } from "react";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { NeedsAttention } from "@/components/dashboard/needs-attention";
import { HearingDensityStrip } from "@/components/dashboard/hearing-density-strip";
import { CasesByUrgency } from "@/components/dashboard/cases-by-urgency";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { useDashboard, useUpcomingHearings } from "@/hooks/use-dashboard";
import { useDocuments } from "@/hooks/use-documents";
import { useCases } from "@/hooks/use-cases";
import { getLastDashboardVisit, setLastDashboardVisit } from "@/lib/last-visit";

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
          <div className="text-[#b32e26] text-lg font-medium mb-2">
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
      {/* Needs Your Attention */}
      <NeedsAttention
        hearingsSoon={hearingsSoon}
        ecourtsUpdates={ecourtsUpdates}
        failedDocuments={failedDocuments}
      />

      {/* Next 14 Days density strip */}
      <HearingDensityStrip hearings={upcomingHearings} />

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
