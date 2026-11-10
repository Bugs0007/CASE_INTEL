"use client";

import { pluralize } from "@/lib/utils";
import { useEffect, useRef, useState, useMemo } from "react";
import Link from "next/link";
import { Search } from "lucide-react";
import { CaseFilters } from "@/components/cases/case-filters";
import { CaseGrid } from "@/components/cases/case-grid";
import { CaseGroupList } from "@/components/cases/case-group-list";
import { GroupByControl } from "@/components/cases/group-by-control";
import { MobileCaseSearch, MobileStatusTabs } from "@/components/cases/mobile/mobile-case-filters";
import {
  MobileGroupChip,
  MobileViewOptionsButton,
  MobileViewOptionsSheet,
} from "@/components/cases/mobile/mobile-group-options";
import { CasesSkeleton } from "@/components/cases/cases-skeleton";
import { MobileSubbar } from "@/components/layout/mobile-chrome";
import { CASES_TABS, SectionTabs } from "@/components/layout/section-tabs";
import { showToast } from "@/components/ui/toaster";
import { useCases, useDeleteCase } from "@/hooks/use-cases";
import { useCasesGrouping, useCollapsedGroups } from "@/hooks/use-cases-grouping";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { useUpcomingHearings } from "@/hooks/use-dashboard";
import { useDocuments } from "@/hooks/use-documents";
import { getLastDashboardVisit } from "@/lib/last-visit";
import { groupCases } from "@/lib/case-grouping";
import { reasonForCase, sortByUrgencyPriority, type UrgencyReason } from "@/lib/case-urgency";
import { istDayKey } from "@/lib/dashboard/dates";
import type { CaseStatus } from "@/types";

export default function CasesPage() {
  const [activeStatus, setActiveStatus] = useState<CaseStatus | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [othersExpanded, setOthersExpanded] = useState(false);
  const isMobile = useIsMobile();
  const { grouping, setGrouping } = useCasesGrouping();
  const { collapsed, toggle: toggleGroup, setAll: setAllGroups } = useCollapsedGroups(grouping);
  const [optionsOpen, setOptionsOpen] = useState(false);

  // Read (never write) the same "since last visit" marker the Dashboard
  // sets, so a case's urgency status agrees between the two screens.
  const [since, setSince] = useState<string | undefined>(undefined);
  useEffect(() => {
    setSince(getLastDashboardVisit() ?? undefined);
  }, []);

  const { data: cases = [], isLoading, error } = useCases(activeStatus, since);

  // Switching the status filter queries a fresh, uncached react-query key,
  // so `isLoading` goes true again on every never-before-visited tab. Only
  // the very first load should swap in the full-page skeleton -- after
  // that, keep the filter bar (and its sliding tab indicator) mounted and
  // let CaseGrid's own isLoading skeleton cover the results area instead.
  const hasLoadedOnce = useRef(false);
  useEffect(() => {
    if (!isLoading) hasLoadedOnce.current = true;
  }, [isLoading]);
  const { data: upcomingHearings = [] } = useUpcomingHearings();
  const { data: ecourtsUpdates = [] } = useUpcomingHearings(since);
  const { data: failedDocuments = [] } = useDocuments({ processing_status: "failed" });
  const deleteCase = useDeleteCase();

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

  const handleDeleteCase = async (id: number) => {
    if (!confirm("Are you sure you want to delete this case? This cannot be undone.")) {
      return;
    }

    try {
      await deleteCase.mutateAsync(id);
      showToast.success("Case deleted", "The case has been removed.");
    } catch (error) {
      console.error("Failed to delete case:", error);
      showToast.error("Delete failed", "Could not delete the case.");
    }
  };

  // Filter cases by search query
  const filteredCases = useMemo(() => {
    if (!searchQuery.trim()) return cases;

    const query = searchQuery.toLowerCase();
    return cases.filter(
      (caseItem) =>
        caseItem.title.toLowerCase().includes(query) ||
        caseItem.case_number.toLowerCase().includes(query) ||
        caseItem.cnr_number?.toLowerCase().includes(query) ||
        caseItem.client_contacts.some((c) => c.name.toLowerCase().includes(query)) ||
        caseItem.opposing_party?.toLowerCase().includes(query),
    );
  }, [cases, searchQuery]);

  const needsAttentionCases = useMemo(
    () => sortByUrgencyPriority(filteredCases.filter((c) => c.needs_attention)),
    [filteredCases],
  );
  const otherCases = useMemo(
    () => filteredCases.filter((c) => !c.needs_attention),
    [filteredCases],
  );
  const urgencyReasons = useMemo(() => {
    const map = new Map<number, UrgencyReason>();
    for (const c of needsAttentionCases) {
      map.set(c.id, reasonForCase(c.id, hearingSoonCaseIds, ecourtsUpdateCaseIds, failedDocCaseIds));
    }
    return map;
  }, [needsAttentionCases, hearingSoonCaseIds, ecourtsUpdateCaseIds, failedDocCaseIds]);

  // Grouped by court or client, the Needs Attention split gives way to one
  // list of groups: a group's count must be every case it holds on screen. The
  // cards keep their urgency chips, and keep the page's order within a group
  // (needs-attention first, then the rest).
  const today = istDayKey();
  const groups = useMemo(
    () => groupCases([...needsAttentionCases, ...otherCases], grouping, today),
    [needsAttentionCases, otherCases, grouping, today],
  );
  const allGroupsCollapsed = groups.length > 0 && groups.every((g) => collapsed.has(g.key));

  if (isLoading && !hasLoadedOnce.current) {
    return <CasesSkeleton />;
  }

  if (error) {
    return (
      <div className="px-4 sm:px-7 pt-5 sm:pt-7">
        <div className="text-center py-12">
          <div className="text-status-alert text-lg font-medium mb-2">
            Failed to load cases
          </div>
          <div className="text-gray-500 text-sm">
            Please try refreshing the page
          </div>
        </div>
      </div>
    );
  }

  const hasUrgentGroup = needsAttentionCases.length > 0;
  const othersToShow = hasUrgentGroup ? otherCases : filteredCases;

  return (
    <div className="px-4 sm:px-7 pt-4 sm:pt-7 pb-[60px] max-w-[1240px] mx-auto">
      {/* The status tabs live in the phone's top bar, first thing on the page
          (the bar is fixed to the top of the screen). */}
      {isMobile && (
        <MobileSubbar height={44}>
          <MobileStatusTabs active={activeStatus} onChange={setActiveStatus} />
        </MobileSubbar>
      )}
      {/* Cases | Documents are both in the bottom bar on a phone. */}
      <SectionTabs tabs={CASES_TABS} className="max-md:hidden" />
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-[22px] max-md:mb-3.5 gap-3">
        <div className="min-w-0">
          <h1 className="text-page-title max-md:!text-[26px] max-md:!leading-[1.1] text-gray-900 mb-1.5 max-md:mb-0.5">Cases</h1>
          <p className="text-sm text-gray-600">
            {pluralize(filteredCases.length, "case")} across your workspace
          </p>
        </div>
        <div className="grid grid-cols-2 sm:flex items-center gap-2">
          <Link
            href="/cases/new"
            className="inline-flex items-center justify-center gap-2 h-11 sm:h-10 px-4 rounded-lg border border-gray-200 bg-surface text-gray-800 text-sm font-semibold hover:bg-gray-50 transition-colors"
          >
            Add Manually
          </Link>
          <Link
            href="/cases/search"
            className="inline-flex items-center justify-center gap-2 h-11 sm:h-10 px-4 rounded-lg border-none bg-primary text-white text-sm font-semibold hover:bg-primary-hover transition-colors"
          >
            <Search className="h-4 w-4" />
            Search by Advocate
          </Link>
        </div>
      </div>

      {/* Filters -- a phone gets a big search field here and the status tabs
          pinned under the top bar, so both stay in reach while scrolling. */}
      {isMobile ? (
        <div className="mb-3">
          <div className="flex items-center gap-2">
            <div className="min-w-0 flex-1">
              <MobileCaseSearch value={searchQuery} onChange={setSearchQuery} />
            </div>
            <MobileViewOptionsButton onClick={() => setOptionsOpen(true)} active={grouping !== "none"} />
          </div>
          {grouping !== "none" && (
            <div className="-mb-1 mt-0.5">
              <MobileGroupChip grouping={grouping} onClick={() => setOptionsOpen(true)} />
            </div>
          )}
          <MobileViewOptionsSheet
            open={optionsOpen}
            onClose={() => setOptionsOpen(false)}
            grouping={grouping}
            onGroupingChange={setGrouping}
          />
        </div>
      ) : (
        <div className="mb-6">
          <CaseFilters
            activeStatus={activeStatus}
            onStatusChange={setActiveStatus}
            onSearchChange={setSearchQuery}
            trailing={<GroupByControl value={grouping} onChange={setGrouping} />}
          />
        </div>
      )}

      {/* Grouped by court or client: one list of groups instead of the two
          sections below. */}
      {grouping !== "none" && (
        <div>
          <div className="mb-3.5 flex items-center justify-between gap-3 max-md:mb-1">
            <h2 className="min-w-0 truncate text-card-title text-gray-900">
              Cases by {grouping}
              {!isLoading && (
                <span className="ml-2.5 text-[13px] font-normal text-gray-500">
                  {pluralize(groups.length, grouping)}
                </span>
              )}
            </h2>
            {!isLoading && groups.length > 0 && (
              <button
                type="button"
                onClick={() => setAllGroups(groups.map((g) => g.key), !allGroupsCollapsed)}
                className="-mr-2 flex h-11 flex-shrink-0 items-center px-2 text-[13px] font-semibold text-primary hover:text-primary-hover md:mr-0 md:h-8 md:px-0"
              >
                {allGroupsCollapsed ? "Expand all" : "Collapse all"}
              </button>
            )}
          </div>
          {isLoading || groups.length === 0 ? (
            <CaseGrid cases={[]} isLoading={isLoading} />
          ) : (
            <CaseGroupList
              groups={groups}
              today={today}
              collapsed={collapsed}
              onToggle={toggleGroup}
              onDelete={handleDeleteCase}
              deletingId={deleteCase.variables}
              urgencyReasons={urgencyReasons}
            />
          )}
        </div>
      )}

      {/* Needs Attention This Week */}
      {grouping === "none" && !isLoading && hasUrgentGroup && (
        <div className="mb-8 max-md:mt-3 max-md:mb-6">
          <div className="flex items-center gap-2.5 mb-3.5 max-md:mb-2.5">
            <h2 className="text-card-title text-gray-900">Needs Attention This Week</h2>
            <span className="ci-chip ci-chip--pending">
              {needsAttentionCases.length}
            </span>
          </div>
          <CaseGrid
            cases={needsAttentionCases}
            onDelete={handleDeleteCase}
            deletingId={deleteCase.variables}
            urgencyReasons={urgencyReasons}
          />
        </div>
      )}

      {/* All Other Cases -- collapsed by default, matching the design
          handoff's toggle behavior (was previously always-expanded). */}
      {grouping === "none" && (
      <div>
        <div className="flex items-center justify-between mb-3.5">
          <h2 className="text-card-title text-gray-900">
            {hasUrgentGroup ? "All Other Cases" : "Cases"}
          </h2>
          {hasUrgentGroup && (
            <button
              onClick={() => setOthersExpanded((v) => !v)}
              className="text-[13px] font-semibold text-primary hover:text-primary-hover"
            >
              {othersExpanded ? "Collapse" : "View All"}
            </button>
          )}
        </div>

        {hasUrgentGroup && !othersExpanded ? (
          <div className="bg-white border border-gray-100 rounded-xl px-5 py-4 text-sm text-gray-600">
            <span className="font-semibold text-gray-900">
              {othersToShow.length} case{othersToShow.length === 1 ? "" : "s"}
            </span>{" "}
            with nothing urgent to review this week.
          </div>
        ) : (
          <CaseGrid
            cases={othersToShow}
            isLoading={isLoading}
            onDelete={handleDeleteCase}
            deletingId={deleteCase.variables}
          />
        )}
      </div>
      )}

      {/* Results Count */}
      {!isLoading && (
        <div className="mt-6 text-center text-sm text-gray-500">
          Showing {filteredCases.length}{" "}
          {filteredCases.length === 1 ? "case" : "cases"}
          {searchQuery && ` matching "${searchQuery}"`}
        </div>
      )}
    </div>
  );
}
