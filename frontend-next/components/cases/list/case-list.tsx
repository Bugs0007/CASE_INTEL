"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { CaseOptionsMenu } from "@/components/cases/list/case-options-menu";
import { attentionReasons, hearingCell, type AttentionContext } from "@/components/cases/list/model";
import { useIsMobile } from "@/hooks/use-is-mobile";
import { cn, hasPlaceholderTitle, primaryClientContact } from "@/lib/utils";
import type { Case } from "@/types";

interface CaseListProps {
  cases: Case[];
  attention: AttentionContext;
  isLoading?: boolean;
  onDelete?: (id: number) => void;
  deletingId?: number;
  /** Hide the column headings (a group header already sits above). */
  bare?: boolean;
}

// Case | Next hearing | Client | Docs | Attention | menu
const COLUMNS = "md:grid-cols-[minmax(0,2.6fr)_minmax(0,1.2fr)_minmax(0,1.4fr)_48px_minmax(0,1.6fr)_32px]";

function clientName(c: Case): string {
  return c.client_detail?.name ?? primaryClientContact(c.client_contacts)?.name ?? "";
}

/** The cases as dense rows: one line each on a phone, a table row from md up.
 * The title is a link stretched over the whole row, so the row opens the case
 * by click and by keyboard; the kebab sits above it. */
export function CaseList({ cases, attention, isLoading, onDelete, deletingId, bare }: CaseListProps) {
  const isMobile = useIsMobile();

  if (isLoading) {
    return (
      <div className="flex flex-col gap-px">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="ci-skeleton h-12 bg-gray-200/60" />
        ))}
      </div>
    );
  }

  if (cases.length === 0) {
    return (
      <div className="text-center py-12">
        <div className="text-6xl mb-4">⚖️</div>
        <h3 className="text-lg font-medium text-gray-900 mb-2">No cases found</h3>
        <p className="text-gray-500">Try adjusting your filters or create a new case.</p>
      </div>
    );
  }

  return (
    <div data-testid="case-list" className="overflow-hidden rounded-xl border border-gray-100 bg-surface">
      {!bare && !isMobile && (
        <div
          aria-hidden="true"
          className={cn(
            "grid items-center gap-3 border-b border-gray-100 bg-gray-50 px-4 py-2 text-[11px] font-semibold uppercase tracking-wide text-gray-500",
            COLUMNS,
          )}
        >
          <span>Case</span>
          <span>Next hearing</span>
          <span>Client</span>
          <span className="text-right">Docs</span>
          <span>Attention</span>
          <span />
        </div>
      )}
      <ul className="divide-y divide-gray-100">
        {cases.map((c) => (
          <CaseRow
            key={c.id}
            c={c}
            attention={attention}
            mobile={isMobile}
            onDelete={onDelete}
            isDeleting={deletingId === c.id}
          />
        ))}
      </ul>
    </div>
  );
}

function CaseRow({
  c,
  attention,
  mobile,
  onDelete,
  isDeleting,
}: {
  c: Case;
  attention: AttentionContext;
  mobile: boolean;
  onDelete?: (id: number) => void;
  isDeleting: boolean;
}) {
  const untitled = hasPlaceholderTitle(c);
  const hearing = hearingCell(c, attention.today);
  const reasons = attentionReasons(c, attention);
  const client = clientName(c);
  const link = (
    <Link
      href={`/cases/${c.id}`}
      className={cn(
        "block truncate font-semibold after:absolute after:inset-0",
        untitled ? "text-gray-400" : "text-gray-900",
        mobile ? "text-[14.5px]" : "text-[14px]",
      )}
    >
      {untitled ? "Untitled matter" : c.title}
    </Link>
  );
  const menu = (
    <CaseOptionsMenu
      className="relative z-10"
      onDelete={() => onDelete?.(c.id)}
      isDeleting={isDeleting}
    />
  );

  if (mobile) {
    return (
      <li data-testid="case-row" className="relative flex min-h-[52px] items-center gap-2 py-1 pl-3 pr-1 active:bg-gray-50">
        <div className="min-w-0 flex-1">
          {link}
          <div className="truncate text-[12px] text-gray-500">
            {hearing.date ? `${hearing.upcoming ? "" : "Last listed "}${hearing.relative}` : "No hearing"}
          </div>
        </div>
        {reasons.length > 0 && (
          <span
            role="img"
            aria-label={reasons.map((r) => r.label).join(", ")}
            className={cn(
              "flex-shrink-0",
              reasons[0].tone === "alert" ? "text-status-alert" : "text-[color:var(--ci-warn)]",
            )}
          >
            <AlertTriangle className="h-4 w-4" aria-hidden="true" />
          </span>
        )}
        {menu}
      </li>
    );
  }

  return (
    <li
      data-testid="case-row"
      className={cn("relative grid items-center gap-3 px-4 py-2 hover:bg-gray-50 transition-colors", COLUMNS)}
    >
      <div className="min-w-0">
        {link}
        <div className="truncate text-[12px] text-gray-500">
          <span className="font-mono">{c.case_number}</span>
          {c.court_name ? <span> · {c.court_name}</span> : null}
        </div>
      </div>
      <div className="min-w-0 text-[13px]">
        {hearing.date ? (
          <>
            <div className={cn("truncate", hearing.upcoming ? "text-gray-900" : "text-gray-500")}>
              {hearing.upcoming ? hearing.date : `Last listed ${hearing.date}`}
            </div>
            <div className={cn("truncate text-[12px]", hearing.soon ? "font-semibold text-[color:var(--ci-warn)]" : "text-gray-500")}>
              {hearing.relative}
            </div>
          </>
        ) : (
          <span className="text-gray-400" aria-label="No hearing">
            {"—"}
          </span>
        )}
      </div>
      <div className="truncate text-[13px] text-gray-700">{client}</div>
      <div className="text-right text-[13px] tabular-nums text-gray-700">{c.document_count}</div>
      <div className="flex min-w-0 flex-wrap items-center gap-1" data-testid="case-attention">
        {reasons.slice(0, 2).map((r) => (
          <span
            key={r.kind}
            className={cn(
              "inline-flex max-w-full items-center gap-1 truncate text-[12px]",
              r.tone === "alert" ? "text-status-alert" : r.tone === "pending" ? "text-[color:var(--ci-warn)]" : "text-gray-600",
            )}
          >
            {r.tone !== "none" && <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" aria-hidden="true" />}
            <span className="truncate">{r.label}</span>
          </span>
        ))}
        {reasons.length > 2 && <span className="text-[12px] text-gray-500">+{reasons.length - 2}</span>}
      </div>
      {menu}
    </li>
  );
}
