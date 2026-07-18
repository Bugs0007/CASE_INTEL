"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { Plus } from "lucide-react";
import { CaseFilters } from "@/components/cases/case-filters";
import { CaseGrid } from "@/components/cases/case-grid";
import { CasesSkeleton } from "@/components/cases/cases-skeleton";
import { showToast } from "@/components/ui/toaster";
import { useCases, useDeleteCase } from "@/hooks/use-cases";
import { useUpcomingHearings } from "@/hooks/use-dashboard";
import { useDocuments } from "@/hooks/use-documents";
import { useDialogs } from "@/providers/dialog-provider";
import { getLastDashboardVisit } from "@/lib/last-visit";
import { reasonForCase, sortByUrgencyPriority, type UrgencyReason } from "@/lib/case-urgency";
import type { CaseStatus } from "@/types";

export default function CasesPage() {
  const [activeStatus, setActiveStatus] = useState<CaseStatus | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [othersExpanded, setOthersExpanded] = useState(false);
  const { openCreateCase } = useDialogs();

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
        caseItem.client_name.toLowerCase().includes(query) ||
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

  if (isLoading && !hasLoadedOnce.current) {
    return <CasesSkeleton />;
  }

  if (error) {
    return (
      <div className="px-7 pt-7">
        <div className="text-center py-12">
          <div className="text-[#b32e26] text-lg font-medium mb-2">
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
    <div className="px-7 pt-7 pb-[60px] max-w-[1240px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-[22px] flex-wrap gap-3">
        <div>
          <h1 className="text-page-title text-gray-900 mb-1.5">Cases</h1>
          <p className="text-sm text-gray-600">
            {filteredCases.length} cases across your workspace
          </p>
        </div>
        <button
          onClick={openCreateCase}
          className="inline-flex items-center gap-2 h-10 px-4 rounded-lg border-none bg-primary text-white text-sm font-semibold hover:bg-primary-hover transition-colors"
        >
          <Plus className="h-4 w-4" />
          New Case
        </button>
      </div>

      {/* Filters */}
      <div className="mb-6">
        <CaseFilters
          activeStatus={activeStatus}
          onStatusChange={setActiveStatus}
          onSearchChange={setSearchQuery}
        />
      </div>

      {/* Needs Attention This Week */}
      {!isLoading && hasUrgentGroup && (
        <div className="mb-8">
          <div className="flex items-center gap-2.5 mb-3.5">
            <h2 className="text-card-title text-gray-900">Needs Attention This Week</h2>
            <span className="inline-flex items-center h-5 px-2 rounded-full bg-[#fdf0e4] text-[#9a4a12] text-xs font-bold">
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
            with nothing due this week — nothing urgent to review.
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
