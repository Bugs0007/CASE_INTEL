"use client";

import { Suspense, useState, useMemo } from "react";
import { Button } from "@/components/ui/button";
import { CaseFilters } from "@/components/cases/case-filters";
import { CaseGrid } from "@/components/cases/case-grid";
import { AiAssistantHintBanner } from "@/components/cases/ai-assistant-hint-banner";
import { showToast } from "@/components/ui/toaster";
import { useCases, useDeleteCase } from "@/hooks/use-cases";
import { useDialogs } from "@/providers/dialog-provider";
import { Plus } from "lucide-react";
import type { CaseStatus } from "@/types";

export default function CasesPage() {
  const [activeStatus, setActiveStatus] = useState<CaseStatus | "all">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const { openCreateCase } = useDialogs();

  const { data: cases = [], isLoading, error } = useCases(activeStatus);
  const deleteCase = useDeleteCase();

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

  if (error) {
    return (
      <div className="p-6">
        <div className="text-center py-12">
          <div className="text-red-500 text-lg font-medium mb-2">
            Failed to load cases
          </div>
          <div className="text-gray-500 text-sm">
            Please try refreshing the page
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <Suspense fallback={null}>
        <AiAssistantHintBanner />
      </Suspense>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Cases</h1>
          <p className="text-gray-600 mt-1">
            Manage and track all your legal cases
          </p>
        </div>
        <Button variant="primary" onClick={openCreateCase}>
          <Plus className="h-4 w-4" />
          New Case
        </Button>
      </div>

      {/* Filters */}
      <div className="mb-6">
        <CaseFilters
          activeStatus={activeStatus}
          onStatusChange={setActiveStatus}
          onSearchChange={setSearchQuery}
        />
      </div>

      {/* Cases Grid */}
      <CaseGrid
        cases={filteredCases}
        isLoading={isLoading}
        onDelete={handleDeleteCase}
        deletingId={deleteCase.variables}
      />

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
