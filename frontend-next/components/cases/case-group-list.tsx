"use client";

import { useId } from "react";
import { ChevronDown } from "lucide-react";
import { CaseGrid } from "@/components/cases/case-grid";
import { CaseList } from "@/components/cases/list/case-list";
import type { AttentionContext } from "@/components/cases/list/model";
import type { CasesView } from "@/components/cases/list/use-cases-view";
import { Reveal } from "@/components/mobile/primitives";
import type { CaseGroup } from "@/lib/case-grouping";
import type { UrgencyReason } from "@/lib/case-urgency";
import { dateLabel } from "@/lib/dashboard/dates";
import { cn, staggerDelay } from "@/lib/utils";

interface CaseGroupListProps {
  groups: CaseGroup[];
  /** The India day "next hearing" is read against (YYYY-MM-DD). */
  today: string;
  /** Keys of the groups that are folded away. */
  collapsed: ReadonlySet<string>;
  onToggle: (key: string) => void;
  onDelete?: (id: number) => void;
  deletingId?: number;
  urgencyReasons?: Map<number, UrgencyReason>;
  /** Dense rows (default) or cards inside each group. */
  view?: CasesView;
  /** What the rows' attention column reads. Needed for the list view. */
  attention: AttentionContext;
}

/** The cases as groups: a header per group (name, how many cases, the soonest
 * hearing) above that group's cards, which are the same cards the plain list
 * uses. A header folds its group; on a phone it stays pinned under the top
 * bar while its group scrolls past. */
export function CaseGroupList({ groups, today, collapsed, onToggle, onDelete, deletingId, urgencyReasons, view = "list", attention }: CaseGroupListProps) {
  return (
    <div data-testid="case-groups" className={cn("flex flex-col max-md:gap-4", view === "list" ? "gap-5" : "gap-7")}>
      {groups.map((group, index) => (
        <CaseGroupSection
          key={group.key}
          group={group}
          index={index}
          today={today}
          open={!collapsed.has(group.key)}
          onToggle={() => onToggle(group.key)}
          onDelete={onDelete}
          deletingId={deletingId}
          urgencyReasons={urgencyReasons}
          view={view}
          attention={attention}
        />
      ))}
    </div>
  );
}

function CaseGroupSection({
  group,
  index,
  today,
  open,
  onToggle,
  onDelete,
  deletingId,
  urgencyReasons,
  view,
  attention,
}: {
  view: CasesView;
  attention: AttentionContext;
  group: CaseGroup;
  index: number;
  today: string;
  open: boolean;
  onToggle: () => void;
  onDelete?: (id: number) => void;
  deletingId?: number;
  urgencyReasons?: Map<number, UrgencyReason>;
}) {
  const id = useId();
  const headingId = `${id}-heading`;
  const panelId = `${id}-panel`;
  const next = group.nextHearingDay ? `Next: ${dateLabel(group.nextHearingDay, today)}` : "No upcoming hearing";

  return (
    <section aria-labelledby={headingId} data-testid="case-group" data-group-key={group.key}>
      {/* A phone pins the header just under the top bar's tabs (44px), and
          under the bar itself while that is showing; the bar slides away on
          the way down, so the offset follows it. (A sticky offset counts from
          inside the page scroller's top padding, which is the bar's height.) */}
      <h3
        id={headingId}
        style={staggerDelay(index, 40, 4)}
        className={cn(
          "animate-fade-up border-b border-[var(--ci-ink-14)] bg-page !text-[14px] !leading-normal motion-reduce:animate-none",
          "max-md:sticky max-md:z-[4] max-md:animate-rise-in max-md:top-[44px] max-md:transition-[top] max-md:duration-300 max-md:ease-out",
          "max-md:[html[data-chrome=hidden]_&]:top-[calc(44px_-_var(--mobile-header-h))] max-md:motion-reduce:transition-none",
          // The list view pins the header under the 67px app bar on desktop.
          view === "list" && "md:sticky md:top-[67px] md:z-[4]",
        )}
      >
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className="flex min-h-[52px] w-full items-center gap-2.5 px-1 text-left md:min-h-[44px] [--press-scale:0.99]"
        >
          <ChevronDown
            aria-hidden="true"
            className={cn(
              "h-4 w-4 flex-shrink-0 text-gray-500 transition-transform duration-300 motion-reduce:transition-none",
              !open && "-rotate-90",
            )}
          />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-2">
              <span className="truncate font-serif text-[16px] font-bold text-gray-900">{group.label}</span>
              <span className="ci-chip ci-chip--none flex-shrink-0">
                {group.cases.length}
                <span className="sr-only"> {group.cases.length === 1 ? "case" : "cases"}</span>
              </span>
            </span>
            {/* Under the name on a phone, where the row is narrow. */}
            <span className="block truncate text-[12px] text-gray-500 md:hidden">{next}</span>
          </span>
          <span className="hidden flex-shrink-0 text-[12.5px] text-gray-500 md:block">{next}</span>
        </button>
      </h3>
      {/* The clip box is a little wider than the cards, so a card's hover lift
          and shadow are not cut off at its edge. */}
      <Reveal open={open} className="-mx-2">
        <div id={panelId} className="px-2 pb-2 pt-3 max-md:pt-2.5">
          {view === "list" ? (
            <CaseList cases={group.cases} attention={attention} onDelete={onDelete} deletingId={deletingId} bare />
          ) : (
            <CaseGrid
              cases={group.cases}
              onDelete={onDelete}
              deletingId={deletingId}
              urgencyReasons={urgencyReasons}
            />
          )}
        </div>
      </Reveal>
    </section>
  );
}
