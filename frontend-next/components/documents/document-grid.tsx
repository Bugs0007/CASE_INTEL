"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Select } from "@/components/ui/select";
import { cn, pluralize } from "@/lib/utils";
import { DocumentCard } from "./document-card";
import { groupByCase, sortDocuments, type DocumentGroup, type GroupBy, type SortDir, type SortKey } from "./list/model";
import type { Document } from "@/types";

interface DocumentGridProps {
  documents: Document[];
  isLoading?: boolean;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  onView: (id: number) => void;
  processingId?: number;
  viewingId?: number;
}

const SORTS = {
  newest: { label: "Newest", key: "date", dir: "desc" },
  oldest: { label: "Oldest", key: "date", dir: "asc" },
  name: { label: "Name", key: "name", dir: "asc" },
  size: { label: "Size", key: "size", dir: "desc" },
} as const satisfies Record<string, { label: string; key: SortKey; dir: SortDir }>;
type SortChoice = keyof typeof SORTS;

const GRID = "grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3";

/** Loading state: cards, not rows. */
export function DocumentGridSkeleton() {
  return (
    <div className={GRID} aria-hidden="true">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="ci-card h-[168px] animate-pulse p-[18px]">
          <div className="mb-3 h-8 w-24 rounded bg-gray-100" />
          <div className="mb-2 h-4 w-3/4 rounded bg-gray-100" />
          <div className="h-3 w-1/2 rounded bg-gray-100" />
        </div>
      ))}
    </div>
  );
}

export function DocumentGrid({
  documents,
  isLoading,
  onProcess,
  onDelete,
  onEdit,
  onView,
  processingId,
  viewingId,
}: DocumentGridProps) {
  const [groupBy, setGroupBy] = useState<GroupBy>("none");
  const [sortChoice, setSortChoice] = useState<SortChoice>("newest");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const sorted = useMemo(
    () => sortDocuments(documents, SORTS[sortChoice].key, SORTS[sortChoice].dir),
    [documents, sortChoice],
  );
  const groups = useMemo<DocumentGroup[]>(() => (groupBy === "case" ? groupByCase(sorted) : []), [groupBy, sorted]);

  if (isLoading) return <DocumentGridSkeleton />;

  if (documents.length === 0) {
    return (
      <div className="rounded-xl border border-gray-100 bg-white p-12 text-center">
        <div className="mb-4 text-6xl">📄</div>
        <h3 className="mb-2 text-lg font-medium text-gray-900">No documents found</h3>
        <p className="text-gray-500">Upload a document or try adjusting your filters.</p>
      </div>
    );
  }

  const allCollapsed = groups.length > 0 && groups.every((g) => collapsed.has(g.key));
  const sections: DocumentGroup[] = groupBy === "case" ? groups : [{ key: "all", case: null, documents: sorted }];

  function toggleGroup(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <div role="group" aria-label="Group documents by" className="inline-flex items-center gap-1.5 text-[13px] text-gray-600">
            <span>Group by</span>
            {(["case", "none"] as GroupBy[]).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={groupBy === option}
                onClick={() => setGroupBy(option)}
                className={cn(
                  "h-11 rounded-md border px-2.5 text-xs font-semibold md:h-8",
                  groupBy === option
                    ? "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]"
                    : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50",
                )}
              >
                {option === "case" ? "Case" : "None"}
              </button>
            ))}
          </div>
          <label className="inline-flex items-center gap-1.5 text-[13px] text-gray-600">
            <span>Sort by</span>
            <Select
              aria-label="Sort by"
              value={sortChoice}
              onChange={(event) => setSortChoice(event.target.value as SortChoice)}
              className="h-11 w-auto text-xs md:h-8"
            >
              {(Object.keys(SORTS) as SortChoice[]).map((choice) => (
                <option key={choice} value={choice}>
                  {SORTS[choice].label}
                </option>
              ))}
            </Select>
          </label>
        </div>
        {groupBy === "case" && (
          <button
            type="button"
            onClick={() => setCollapsed(allCollapsed ? new Set() : new Set(groups.map((g) => g.key)))}
            className="h-11 rounded-md border border-gray-200 bg-white px-2.5 text-xs font-semibold text-gray-700 hover:bg-gray-50 md:h-8"
          >
            {allCollapsed ? "Expand all" : "Collapse all"}
          </button>
        )}
      </div>

      <div className="flex flex-col gap-4">
        {sections.map((group) => (
          <section key={group.key} aria-label={groupLabel(group)} className="flex flex-col gap-2.5">
            {groupBy === "case" && (
              <GroupHeader group={group} open={!collapsed.has(group.key)} onToggle={() => toggleGroup(group.key)} />
            )}
            {!collapsed.has(group.key) && (
              <div className={GRID}>
                {group.documents.map((doc, i) => (
                  <DocumentCard
                    key={doc.id}
                    document={doc}
                    index={i}
                    onProcess={onProcess}
                    onDelete={onDelete}
                    onEdit={onEdit}
                    onView={onView}
                    isProcessing={processingId === doc.id}
                    isViewing={viewingId === doc.id}
                  />
                ))}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}

function groupLabel(group: DocumentGroup): string {
  return group.case ? group.case.title : group.key === "none" ? "No case" : "Documents";
}

function GroupHeader({ group, open, onToggle }: { group: DocumentGroup; open: boolean; onToggle: () => void }) {
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div className="flex items-center gap-2 rounded-lg border border-gray-100 bg-[var(--ci-paper-2)] px-3 py-1.5">
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        aria-label={`${open ? "Collapse" : "Expand"} ${groupLabel(group)}`}
        className="flex h-11 min-w-0 flex-1 items-center gap-2 text-left md:h-8"
      >
        <Chevron className="h-4 w-4 flex-shrink-0 text-gray-500" aria-hidden="true" />
        <span className="min-w-0 truncate font-serif text-[14px] font-semibold text-gray-900">{groupLabel(group)}</span>
        {group.case && <span className="flex-shrink-0 font-mono text-[11.5px] text-gray-500">{group.case.case_number}</span>}
        <span className="flex-shrink-0 text-[12px] text-gray-500">{pluralize(group.documents.length, "document")}</span>
      </button>
      {group.case && (
        <Link href={`/cases/${group.case.id}`} className="flex-shrink-0 text-xs font-semibold text-primary hover:text-primary-hover">
          Open case
        </Link>
      )}
    </div>
  );
}
