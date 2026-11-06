"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CalendarClock, Check, FilePlus2, FileText, IndianRupee, Mail, Play, Plus, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CompactCard } from "@/components/cases/compact/compact-card";
import { CaseFeesCard } from "@/components/cases/case-fees-card";
import { ClientContactsCard } from "@/components/cases/client-contacts-card";
import { NextHearingCard } from "@/components/cases/next-hearing-card";
import { UpdateRecipientsNote } from "@/components/cases/case-banners";
import { CaseClientUpdatesCard } from "@/components/client-updates/case-client-updates-card";
import { CauseListBadge } from "@/components/hearings/cause-list-badge";
import { DocumentStatusBadge, isDocumentActive } from "@/components/documents/document-status-badge";
import { TasksCard } from "@/components/tasks/tasks-card";
import { AddTaskDialog } from "@/components/dashboard/add-task-dialog";
import { useClientMessages } from "@/hooks/use-clients";
import { useTasks } from "@/hooks/use-tasks";
import { hearingDayKey } from "@/lib/calendar";
import { latestOrderDocument, matchesQuery, nextHearing, previewDocuments, previewTasks, sortDocuments } from "@/lib/case-previews";
import { istDayKey, daysBetween } from "@/lib/dashboard/dates";
import { daysUntilDate, dueChipVariant, dueLabel } from "@/lib/tasks";
import { cn, formatINR } from "@/lib/utils";
import type { Case, CourtType, Document, Hearing } from "@/types";

// ---------------------------------------------------------------------------
// Next hearing
// ---------------------------------------------------------------------------

export function CompactNextHearing({ hearings }: { hearings: Hearing[] }) {
  const hearing = nextHearing(hearings);
  const day = hearing ? hearingDayKey(hearing.hearing_date) : null;
  const until = day ? daysBetween(istDayKey(), day) : null;
  const month = day ? new Date(Number(day.slice(0, 4)), Number(day.slice(5, 7)) - 1, Number(day.slice(8, 10))) : null;

  return (
    <CompactCard
      id="next-hearing"
      title="Next hearing"
      icon={<CalendarClock className="h-4 w-4" />}
      dialog={{ children: <NextHearingCard hearings={hearings} /> }}
    >
      {!hearing || !day || !month ? (
        <p className="px-4 py-3 text-[13.5px] text-gray-500">No upcoming hearing is scheduled.</p>
      ) : (
        <div className="px-4 py-2">
          <div className="flex items-center gap-3">
            <span className="font-serif text-[34px] font-bold leading-none text-gray-900">{Number(day.slice(8, 10))}</span>
            <span className="text-[13px] leading-tight text-gray-600">
              {month.toLocaleString("en-GB", { month: "short" })} {day.slice(0, 4)}
              <br />
              {month.toLocaleString("en-GB", { weekday: "long" })}
            </span>
            <span className="ci-chip ci-chip--pending ml-auto">
              {until === null || until <= 0 ? "today" : until === 1 ? "tomorrow" : `in ${until} days`}
            </span>
          </div>
          {hearing.location && (
            <div className="mt-1 flex h-[22px] items-center justify-between gap-3 border-b border-dashed border-gray-200 text-[13px]">
              <span className="text-gray-600">Court</span>
              <span className="min-w-0 truncate font-semibold text-gray-900">{hearing.location}</span>
            </div>
          )}
          <div className="mt-1 flex h-[22px] items-center justify-between gap-3 text-[13px]">
            <span className="text-gray-600">Cause list</span>
            <CauseListBadge hearing={hearing} />
          </div>
        </div>
      )}
    </CompactCard>
  );
}

// ---------------------------------------------------------------------------
// Tasks & deadlines
// ---------------------------------------------------------------------------

export function CompactTasks({
  caseId,
  caseTitle,
  courtType,
  latestOrder,
  rows,
}: {
  caseId: number;
  caseTitle: string;
  courtType: CourtType | null;
  latestOrder: { id: number; order_date: string } | null;
  rows: number;
}) {
  const { data: tasks = [] } = useTasks({ case_id: caseId });
  const [adding, setAdding] = useState(false);
  const shown = previewTasks(tasks, rows);

  return (
    <>
      <CompactCard
        id="tasks"
        title="Tasks & Deadlines"
        icon={<Check className="h-4 w-4" />}
        actions={
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            <Plus className="h-3.5 w-3.5" />
            Task
          </Button>
        }
        dialog={{ title: "Tasks & Deadlines", children: <TasksCard caseId={caseId} courtType={courtType} latestOrder={latestOrder} /> }}
      >
        {shown.length === 0 ? (
          <p className="px-4 py-3 text-[13.5px] text-gray-500">Nothing due on this case.</p>
        ) : (
          <ul>
            {shown.map((task) => {
              const days = task.due_date ? daysUntilDate(task.due_date) : null;
              return (
                <li key={task.id} className="flex h-9 items-center gap-2 border-b border-gray-100 px-4 last:border-b-0">
                  <span className="min-w-0 flex-1 truncate text-[13px] text-gray-900">{task.title}</span>
                  {days !== null && (
                    <span className={`ci-chip ci-chip--${dueChipVariant(days)} flex-shrink-0`}>{dueLabel(days)}</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {tasks.filter((t) => t.status === "pending" || t.status === "in_progress").length > shown.length && (
          <p className="px-4 pb-1.5 text-xs text-gray-500">
            + {tasks.filter((t) => t.status === "pending" || t.status === "in_progress").length - shown.length} more in the expanded view
          </p>
        )}
      </CompactCard>
      <AddTaskDialog caseId={adding ? caseId : null} caseTitle={caseTitle} onClose={() => setAdding(false)} />
    </>
  );
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

const isOrderDoc = (d: Document) => d.document_type === "court_order" || d.document_type === "order";

function typeLabel(d: Document): string {
  if (isOrderDoc(d)) return "ORDER";
  if (d.document_type === "pleading" || d.document_type === "motion" || d.document_type === "brief") return "FILING";
  return (d.document_type ?? "file").replace(/_/g, " ").toUpperCase();
}

function docDate(d: Document): string {
  const day = (d.document_date ?? d.created_at).slice(0, 10);
  const [y, m, dd] = day.split("-").map(Number);
  return new Date(y ?? 1970, (m ?? 1) - 1, dd ?? 1).toLocaleString("en-GB", { day: "2-digit", month: "short" }).toUpperCase();
}

interface CompactDocumentsProps {
  documents: Document[];
  isLoading: boolean;
  rows: number;
  onUploadClick: () => void;
  onGenerateClick?: () => void;
  onView: (id: number) => void;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  isProcessPending: boolean;
  processingDocId?: number;
  /** One plain line under the rows about the order check (see order sync). */
  statusLine?: React.ReactNode;
}

export function CompactDocuments({
  documents,
  isLoading,
  rows,
  onUploadClick,
  onGenerateClick,
  onView,
  onProcess,
  onDelete,
  isProcessPending,
  processingDocId,
  statusLine,
}: CompactDocumentsProps) {
  const shown = previewDocuments(documents, rows);
  const [filter, setFilter] = useState<"all" | "orders" | "filings">("all");
  const [query, setQuery] = useState("");
  const pinned = latestOrderDocument(documents)?.id;

  const sorted = useMemo(() => sortDocuments(documents), [documents]);
  const counts = {
    all: documents.length,
    orders: documents.filter(isOrderDoc).length,
    filings: documents.filter((d) => !isOrderDoc(d)).length,
  };
  const visible = sorted
    .filter((d) => (filter === "orders" ? isOrderDoc(d) : filter === "filings" ? !isOrderDoc(d) : true))
    .filter((d) => matchesQuery(query, d.display_name, d.filename, d.document_type));
  const groups: { label: string; docs: Document[] }[] = [
    { label: "Orders", docs: visible.filter(isOrderDoc) },
    { label: "Filings", docs: visible.filter((d) => !isOrderDoc(d)) },
  ];

  const chips = [
    { key: "all" as const, label: "All" },
    { key: "orders" as const, label: "Orders" },
    { key: "filings" as const, label: "Filings" },
  ];

  return (
    <CompactCard
      id="documents"
      className="min-h-0 flex-1"
      title="Documents"
      icon={<FileText className="h-4 w-4" />}
      count={documents.length}
      actions={
        <Button variant="secondary" size="sm" onClick={onUploadClick}>
          <Upload className="h-3.5 w-3.5" />
          Upload
        </Button>
      }
      dialog={{
        count: documents.length,
        actions: (
          <>
            {onGenerateClick && (
              <Button variant="secondary" size="sm" onClick={onGenerateClick}>
                <FilePlus2 className="h-3.5 w-3.5" />
                Generate
              </Button>
            )}
            <Button variant="secondary" size="sm" onClick={onUploadClick}>
              <Upload className="h-3.5 w-3.5" />
              Upload
            </Button>
          </>
        ),
        toolbar: (
          <div className="flex flex-wrap items-center gap-2">
            <div role="group" aria-label="Filter documents" className="flex gap-1.5">
              {chips.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  aria-pressed={filter === chip.key}
                  onClick={() => setFilter(chip.key)}
                  className={cn(
                    "h-8 rounded-full border px-3 text-xs font-bold",
                    filter === chip.key
                      ? "border-[var(--ci-ink)] bg-[var(--ci-ink)] text-[color:var(--ci-paper)]"
                      : "border-gray-200 bg-surface text-gray-600 hover:border-[var(--ci-ink)]",
                  )}
                >
                  {chip.label} {counts[chip.key]}
                </button>
              ))}
            </div>
            <Input
              type="search"
              aria-label="Search documents"
              placeholder="Search documents"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="ml-auto h-8 w-full sm:w-60"
            />
          </div>
        ),
        footer: "Click a document to open it in the viewer",
        children: (
          <div>
            {visible.length === 0 && <p className="py-4 text-sm text-gray-500">No documents match.</p>}
            {groups
              .filter((g) => g.docs.length > 0)
              .map((g) => (
                <section key={g.label} aria-label={g.label}>
                  <h3 className="pb-1 pt-3 font-mono text-[11px] uppercase tracking-[0.1em] text-gray-500">{g.label}</h3>
                  <ul>
                    {g.docs.map((d) => {
                      const canProcess = !isDocumentActive(d) && (d.processing_status === "pending" || d.processing_status === "failed");
                      return (
                        <li key={d.id} className="flex items-center gap-2 border-b border-gray-100">
                          <button
                            type="button"
                            onClick={() => onView(d.id)}
                            className="flex min-h-10 min-w-0 flex-1 items-center gap-3 py-1.5 text-left hover:bg-gray-50"
                          >
                            <FileText className="h-4 w-4 flex-shrink-0 text-gray-500" />
                            <span className="min-w-0 flex-1 truncate text-[13.5px] text-gray-900">{d.display_name || d.filename}</span>
                            {(isDocumentActive(d) || d.processing_status === "failed") && <DocumentStatusBadge document={d} />}
                            <span className="flex-shrink-0 font-mono text-[11px] text-gray-500">{docDate(d)}</span>
                          </button>
                          {canProcess && (
                            <Button variant="ghost" size="sm" onClick={() => onProcess(d.id)} disabled={isProcessPending && processingDocId === d.id} aria-label={`Process ${d.filename}`}>
                              <Play className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          <Button variant="ghost" size="sm" onClick={() => onDelete(d.id)} aria-label={`Delete ${d.filename}`}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
          </div>
        ),
      }}
    >
      {isLoading ? (
        <p className="px-4 py-3 text-sm text-gray-500">Loading documents…</p>
      ) : shown.length === 0 ? (
        <p className="px-4 py-3 text-[13.5px] text-gray-500">No documents yet.</p>
      ) : (
        <ul>
          {shown.map((d) => (
            <li key={d.id}>
              <button
                type="button"
                onClick={() => onView(d.id)}
                className={cn(
                  "flex h-10 w-full items-center gap-3 border-b border-gray-100 px-4 text-left hover:bg-gray-50",
                  d.id === pinned && "font-semibold",
                )}
              >
                <FileText className="h-4 w-4 flex-shrink-0 text-gray-500" />
                <span className="min-w-0 flex-1 truncate text-[13.5px] text-gray-900">{d.display_name || d.filename}</span>
                <span className="flex-shrink-0 font-mono text-[11px] tracking-[0.06em] text-gray-500">{typeLabel(d)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {statusLine && <div className="flex-shrink-0 px-4 py-1 text-xs leading-4 text-gray-500">{statusLine}</div>}
    </CompactCard>
  );
}

// ---------------------------------------------------------------------------
// Fees & billing
// ---------------------------------------------------------------------------

export function CompactFees({ caseItem, hearings }: { caseItem: Case; hearings: Hearing[] }) {
  const s = caseItem.fee_summary;
  const [open, setOpen] = useState(false);
  // Billed: invoiced or paid. Received: paid. Pending: billed or billable and not yet received.
  const billed = Number(s.invoiced_amount) + Number(s.paid_amount);
  const tiles: [string, string][] = [
    ["Billed", formatINR(billed)],
    ["Received", formatINR(s.paid_amount)],
    ["Pending", formatINR(s.outstanding_amount)],
  ];
  return (
    <CompactCard
      id="fees"
      title="Fees & billing"
      icon={<IndianRupee className="h-4 w-4" />}
      open={open}
      onOpenChange={setOpen}
      actions={
        hearings.length > 0 ? (
          <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
            Record fee
          </Button>
        ) : undefined
      }
      dialog={{ children: <CaseFeesCard caseId={caseItem.id} summary={s} hearings={hearings} /> }}
    >
      <div className="grid grid-cols-3 gap-2 px-4 py-2">
        {tiles.map(([label, value]) => (
          <div key={label} className="min-w-0 rounded border border-gray-200 bg-page px-2.5 py-1">
            <div className="font-mono text-[10.5px] uppercase leading-none tracking-[0.08em] text-gray-500">{label}</div>
            <div className="mt-1 truncate font-mono text-[13px] font-bold text-gray-900">{value}</div>
          </div>
        ))}
      </div>
    </CompactCard>
  );
}

// ---------------------------------------------------------------------------
// Client updates
// ---------------------------------------------------------------------------

export function CompactClientUpdates({ caseItem, onEditDetails }: { caseItem: Case; onEditDetails: () => void }) {
  const { data: drafts = [] } = useClientMessages({ case_id: caseItem.id, status: "draft" });
  const recipients = caseItem.update_recipient_count ?? 0;
  return (
    <CompactCard
      id="client-updates"
      title="Client updates"
      icon={<Mail className="h-4 w-4" />}
      dialog={{
        children: (
          <div className="space-y-4">
            <CaseClientUpdatesCard caseId={caseItem.id} />
            <UpdateRecipientsNote caseItem={caseItem} onEditDetails={onEditDetails} />
            <ClientContactsCard contacts={caseItem.client_contacts} onEditDetails={onEditDetails} />
          </div>
        ),
      }}
    >
      <p className="flex items-center justify-between gap-3 px-4 py-2.5 text-[13.5px] text-gray-600">
        <span>
          Updates go out after each hearing. {recipients} recipient{recipients === 1 ? "" : "s"} set.
          {drafts.length > 0 && (
            <>
              {" "}
              <Link href="/messages" className="font-semibold text-gray-900 underline">
                {drafts.length} to review
              </Link>
            </>
          )}
        </span>
        <button type="button" onClick={onEditDetails} className="flex-shrink-0 font-semibold text-gray-900 underline">
          Add
        </button>
      </p>
    </CompactCard>
  );
}
