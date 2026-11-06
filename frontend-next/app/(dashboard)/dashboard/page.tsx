"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { BriefingView } from "@/components/dashboard/briefing-view";
import { DashboardSkeleton } from "@/components/dashboard/dashboard-skeleton";
import { PracticeMap } from "@/components/dashboard/practice-map";
import { RefreshAllButton } from "@/components/dashboard/refresh-all-button";
import { ViewToggle, panelId, tabId } from "@/components/dashboard/view-toggle";
import { showToast } from "@/components/ui/toaster";
import { useAdvocateProfile } from "@/hooks/use-billing";
import { useCases } from "@/hooks/use-cases";
import { useBillingPortfolio, useClientMessages } from "@/hooks/use-clients";
import { useUpcomingHearings } from "@/hooks/use-dashboard";
import { useDashboardView } from "@/hooks/use-dashboard-view";
import { useDocuments } from "@/hooks/use-documents";
import { useHearings } from "@/hooks/use-hearings";
import { useTasks, useUpdateTask } from "@/hooks/use-tasks";
import {
  caseDisplayTitle,
  lastOrdersByCase,
  toChanged,
  toDashCase,
  toDashHearing,
  toDashTasks,
  toDrafts,
  toFailedDocs,
  toUnbilled,
} from "@/lib/dashboard/adapt";
import { greetingFor, istDayKey } from "@/lib/dashboard/dates";
import { buildDashboardModel } from "@/lib/dashboard/model";
import { getLastDashboardVisit, setLastDashboardVisit } from "@/lib/last-visit";
import { pluralize } from "@/lib/utils";

export default function DashboardPage() {
  // useSearchParams (the ?view= choice) needs a Suspense boundary on a
  // prerendered page.
  return (
    <Suspense fallback={<DashboardSkeleton />}>
      <Dashboard />
    </Suspense>
  );
}

function Dashboard() {
  const { view, setView } = useDashboardView();
  const [today] = useState(() => istDayKey());
  const [hour] = useState(() => new Date().getHours());

  // The previous visit's timestamp, read before it is overwritten, so
  // "changed since you last looked" has something to compare against.
  // undefined = not read yet; null = a first visit (nothing to compare with,
  // so nothing is reported as changed).
  const [since, setSince] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    setSince(getLastDashboardVisit());
    setLastDashboardVisit(new Date().toISOString());
  }, []);

  // Everything the page needs, loaded once. Switching views only re-reads
  // this data; it never fetches.
  const cases = useCases("all");
  const hearings = useHearings({});
  const tasks = useTasks({ status: "open" });
  const updates = useUpcomingHearings(since ?? undefined, !!since);
  const failedDocs = useDocuments({ processing_status: "failed" });
  const drafts = useClientMessages({ status: "draft" });
  const billing = useBillingPortfolio();
  const profile = useAdvocateProfile();
  const updateTask = useUpdateTask();

  const model = useMemo(() => {
    const caseList = cases.data ?? [];
    const hearingList = hearings.data ?? [];
    const titles = new Map(caseList.map((c) => [c.id, caseDisplayTitle(c.title, c.case_number)]));
    return buildDashboardModel({
      today,
      cases: caseList.map(toDashCase),
      hearings: hearingList.map((h) => toDashHearing(h, titles)),
      tasks: toDashTasks(tasks.data ?? []),
      changed: since ? toChanged(updates.data ?? []) : [],
      failedDocs: toFailedDocs(failedDocs.data ?? []),
      unbilled: toUnbilled(billing.data?.uninvoiced_hearings ?? []),
      drafts: toDrafts(drafts.data ?? []),
      lastOrders: lastOrdersByCase(hearingList, today),
    });
  }, [today, since, cases.data, hearings.data, tasks.data, updates.data, failedDocs.data, billing.data, drafts.data]);

  const loading =
    since === undefined ||
    cases.isLoading ||
    hearings.isLoading ||
    tasks.isLoading ||
    updates.isLoading ||
    failedDocs.isLoading ||
    drafts.isLoading ||
    billing.isLoading ||
    profile.isLoading;

  if (loading) return <DashboardSkeleton />;

  // The three lists the page cannot make sense without. A failing extra
  // (drafts, billing, failed documents) leaves its part empty instead.
  if (cases.error || hearings.error || tasks.error) {
    return (
      <div className="px-4 pt-5 sm:px-7 sm:pt-7">
        <div className="py-12 text-center">
          <div className="mb-2 text-lg font-medium text-status-alert">Failed to load dashboard</div>
          <div className="text-sm text-gray-500">Please try refreshing the page</div>
        </div>
      </div>
    );
  }

  const firstName = (profile.data?.advocate_name ?? "").trim().split(/\s+/)[0];
  const greeting = `${greetingFor(hour)}${firstName ? `, ${firstName}` : ""}.`;
  const completingTaskId = updateTask.isPending ? updateTask.variables?.id : undefined;

  function completeTask(id: number) {
    updateTask.mutate(
      { id, data: { status: "completed" } },
      { onError: () => showToast.error("Could not update task", "Try again in a moment.") },
    );
  }

  return (
    <div className="@container mx-auto max-w-[1680px] px-4 pb-[60px] pt-5 sm:px-7 sm:pt-7">
      <header className="mb-5 flex flex-wrap items-center gap-x-5 gap-y-3">
        <div className="min-w-0">
          <h1 className="text-page-title text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-600">
            {model.dateLine} · {pluralize(model.activeCaseCount, "active case")}
          </p>
        </div>
        <ViewToggle view={view} onChange={setView} />
        <div className="ml-auto">
          <RefreshAllButton compact />
        </div>
      </header>

      <div role="tabpanel" id={panelId(view)} aria-labelledby={tabId(view)}>
        {view === "brief" ? (
          <BriefingView
            model={model}
            greeting={greeting}
            billing={{ data: billing.data, isLoading: false, error: billing.error }}
            completingTaskId={completingTaskId}
            onCompleteTask={completeTask}
            onOpenMap={() => setView("map")}
          />
        ) : (
          <PracticeMap model={model} />
        )}
      </div>
    </div>
  );
}
