"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { ArrowDown, ArrowUp, ChevronDown, ChevronRight } from "lucide-react";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { cn, pluralize } from "@/lib/utils";
import { DocumentRow } from "./document-row";
import {
  groupByCase,
  sortDocuments,
  type DocumentGroup,
  type GroupBy,
  type SortDir,
  type SortKey,
} from "./list/model";
import type { Document } from "@/types";

interface DocumentTableProps {
  documents: Document[];
  isLoading?: boolean;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  onView: (id: number) => void;
  processingId?: number;
  deletingId?: number;
  viewingId?: number;
}

const COLUMNS: { key: SortKey | null; label: string; className?: string }[] = [
  { key: "name", label: "Name", className: "pl-3" },
  { key: null, label: "Case" },
  { key: "date", label: "Date" },
  { key: "size", label: "Size", className: "text-right" },
  { key: null, label: "Status" },
];

export function DocumentTable({
  documents,
  isLoading,
  onProcess,
  onDelete,
  onEdit,
  onView,
  processingId,
  deletingId,
  viewingId,
}: DocumentTableProps) {
  const isMobile = useIsMobile();
  const [groupBy, setGroupBy] = useState<GroupBy>("case");
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "date", dir: "desc" });
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const sorted = useMemo(() => sortDocuments(documents, sort.key, sort.dir), [documents, sort]);
  const groups = useMemo<DocumentGroup[]>(
    () => (groupBy === "case" ? groupByCase(sorted) : []),
    [groupBy, sorted],
  );

  if (isLoading) {
    return (
      <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        <div className="p-12 text-center text-gray-500">Loading documents...</div>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        <div className="p-12 text-center">
          <div className="text-6xl mb-4">📄</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">No documents found</h3>
          <p className="text-gray-500">Upload a document or try adjusting your filters.</p>
        </div>
      </div>
    );
  }

  const allCollapsed = groups.length > 0 && groups.every((g) => collapsed.has(g.key));

  function toggleSort(key: SortKey) {
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "name" ? "asc" : "desc" }));
  }

  function toggleGroup(key: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const rowProps = (doc: Document, index: number) => ({
    document: doc,
    index,
    onProcess,
    onDelete,
    onEdit,
    onView,
    isProcessing: processingId === doc.id,
    isDeleting: deletingId === doc.id,
    isViewing: viewingId === doc.id,
    // Grouped by case, the group header already names the case.
    showCase: groupBy !== "case",
  });

  const sections: DocumentGroup[] = groupBy === "case" ? groups : [{ key: "all", case: null, documents: sorted }];

  return (
    <div>
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label="Group documents by" className="inline-flex items-center gap-1.5 text-[13px] text-gray-600">
          <span>Group by</span>
          {(["case", "none"] as GroupBy[]).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={groupBy === option}
              onClick={() => setGroupBy(option)}
              className={cn(
                "h-8 rounded-md border px-2.5 text-xs font-semibold",
                groupBy === option ? "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]" : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50",
              )}
            >
              {option === "case" ? "Case" : "None"}
            </button>
          ))}
        </div>
        {groupBy === "case" && (
          <button
            type="button"
            onClick={() => setCollapsed(allCollapsed ? new Set() : new Set(groups.map((g) => g.key)))}
            className="h-8 rounded-md border border-gray-200 bg-white px-2.5 text-xs font-semibold text-gray-700 hover:bg-gray-50"
          >
            {allCollapsed ? "Expand all" : "Collapse all"}
          </button>
        )}
      </div>

      {isMobile ? (
        <div className="flex flex-col gap-2.5">
          {sections.map((group) => (
            <section key={group.key} aria-label={groupLabel(group)} className="flex flex-col gap-2">
              {groupBy === "case" && (
                <GroupHeader group={group} open={!collapsed.has(group.key)} onToggle={() => toggleGroup(group.key)} />
              )}
              {!collapsed.has(group.key) &&
                group.documents.map((doc, i) => <DocumentRow key={doc.id} {...rowProps(doc, i)} />)}
            </section>
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-100 bg-white">
          <table className="w-full table-fixed border-collapse text-left">
            <caption className="sr-only">Documents</caption>
            <colgroup>
              <col className={groupBy === "case" ? "w-auto" : "w-[40%]"} />
              {groupBy !== "case" && <col className="w-[27%]" />}
              <col className="w-[110px]" />
              <col className="w-[76px]" />
              <col className="w-[150px]" />
              <col className="w-10" />
            </colgroup>
            <thead>
              <tr className="text-[11px] font-semibold uppercase tracking-wide text-gray-500">
                {COLUMNS.filter((col) => groupBy !== "case" || col.label !== "Case").map((col) => {
                  const sortKey = col.key;
                  const active = sortKey !== null && sort.key === sortKey;
                  return (
                    <th
                      key={col.label}
                      scope="col"
                      aria-sort={active ? (sort.dir === "asc" ? "ascending" : "descending") : sortKey ? "none" : undefined}
                      className={cn("px-2 py-2", col.className)}
                    >
                      {sortKey ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(sortKey)}
                          className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-gray-900"
                        >
                          {col.label}
                          {active && (sort.dir === "asc" ? <ArrowUp className="h-3 w-3" aria-hidden="true" /> : <ArrowDown className="h-3 w-3" aria-hidden="true" />)}
                        </button>
                      ) : (
                        col.label
                      )}
                    </th>
                  );
                })}
                <th scope="col" className="w-10 px-2 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            {sections.map((group) => (
              <tbody key={group.key}>
                {groupBy === "case" && (
                  <tr className="border-t border-gray-100 bg-[var(--ci-paper-2)]">
                    <td colSpan={5} className="p-0">
                      <GroupHeader group={group} open={!collapsed.has(group.key)} onToggle={() => toggleGroup(group.key)} flat />
                    </td>
                  </tr>
                )}
                {!collapsed.has(group.key) &&
                  group.documents.map((doc, i) => (
                    <DocumentRow key={doc.id} {...rowProps(doc, i)} />
                  ))}
              </tbody>
            ))}
          </table>
        </div>
      )}
    </div>
  );
}

function groupLabel(group: DocumentGroup): string {
  return group.case ? group.case.title : group.key === "none" ? "No case" : "Documents";
}

function GroupHeader({
  group,
  open,
  onToggle,
  flat,
}: {
  group: DocumentGroup;
  open: boolean;
  onToggle: () => void;
  flat?: boolean;
}) {
  const Chevron = open ? ChevronDown : ChevronRight;
  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5",
        !flat && "rounded-lg border border-gray-100 bg-[var(--ci-paper-2)]",
      )}
    >
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        aria-label={`${open ? "Collapse" : "Expand"} ${groupLabel(group)}`}
        className="flex h-8 min-w-0 flex-1 items-center gap-2 text-left max-md:h-11"
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
