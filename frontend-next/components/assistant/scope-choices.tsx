"use client";

import { useEffect, useId, useMemo, useState, type KeyboardEvent } from "react";
import { usePathname } from "next/navigation";
import { Search, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { addDaysToKey, todayDayKey } from "@/components/dashboard/practice/format";
import { useConversationList } from "@/hooks/use-chat";
import { useCases } from "@/hooks/use-cases";
import { buildChooserSections, type ChooserCase } from "@/lib/assistant";
import { PORTFOLIO_BOT_ENABLED } from "@/lib/feature-flags";
import { cn } from "@/lib/utils";
import { caseIdFromPath, type AssistantScope } from "@/providers/assistant-provider";

/** How far ahead "Hearing soon" looks, in days. */
const SOON_DAYS = 7;

interface Option {
  id: string;
  scope: AssistantScope;
  title: string;
  sub: string | null;
  section: string;
}

/** What a chat can be about: the whole practice (when it is switched on) or
 * one of the advocate's cases. One search box, then sections for this page's
 * case, recent cases, hearings in the next week, and every case A to Z. Arrow
 * keys move through the options and Enter picks. */
export function ScopeChoices({
  onPick,
  onCancel,
  className,
}: {
  onPick: (scope: AssistantScope) => void;
  onCancel?: () => void;
  className?: string;
}) {
  const pathname = usePathname();
  const cases = useCases();
  const chats = useConversationList("default");
  const [filter, setFilter] = useState("");
  const [active, setActive] = useState(0);
  const inputId = useId();
  const listId = useId();
  const needle = filter.trim().toLowerCase();

  const today = todayDayKey();
  const sections = useMemo(
    () =>
      buildChooserSections({
        cases: (cases.data ?? []) as ChooserCase[],
        filter,
        pageCaseId: caseIdFromPath(pathname),
        recentCaseIds: [...(chats.data ?? [])]
          .filter((row) => row.case_id !== null)
          .sort((a, b) => Date.parse(b.last_message_at ?? b.started_at) - Date.parse(a.last_message_at ?? a.started_at))
          .map((row) => row.case_id as number),
        today,
        soonUntil: addDaysToKey(today, SOON_DAYS),
      }),
    [cases.data, chats.data, filter, pathname, today],
  );

  const showPractice = PORTFOLIO_BOT_ENABLED && (!needle || "your practice".includes(needle));
  const options: Option[] = useMemo(() => {
    const list: Option[] = [];
    if (showPractice) {
      list.push({ id: "practice", scope: { kind: "practice" }, title: "Your practice", sub: null, section: "practice" });
    }
    for (const section of sections) {
      for (const item of section.cases) {
        list.push({
          id: `${section.key}-${item.id}`,
          scope: { kind: "case", caseId: item.id, caseTitle: item.title, caseNumber: item.case_number },
          title: item.title,
          sub: item.case_number || null,
          section: section.key,
        });
      }
    }
    return list;
  }, [showPractice, sections]);

  useEffect(() => setActive(0), [filter]);
  const activeOption = options[Math.min(active, options.length - 1)];
  useEffect(() => {
    if (!activeOption) return;
    document.getElementById(`${listId}-${activeOption.id}`)?.scrollIntoView?.({ block: "nearest" });
  }, [activeOption, listId]);

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (options.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((value) => Math.min(value + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter" && activeOption) {
      event.preventDefault();
      onPick(activeOption.scope);
    }
  }

  function row(option: Option) {
    const selected = option.id === activeOption?.id;
    return (
      <li
        key={option.id}
        id={`${listId}-${option.id}`}
        role="option"
        aria-selected={selected}
        onClick={() => onPick(option.scope)}
        onMouseMove={() => setActive(options.indexOf(option))}
        className={cn(
          "flex min-h-[44px] cursor-pointer flex-col justify-center rounded-lg px-2 py-1.5 text-left",
          selected ? "bg-gray-100" : "hover:bg-gray-50",
        )}
      >
        <span className="flex w-full items-center gap-2 break-words text-sm font-medium text-gray-900">
          {option.id === "practice" && <User className="h-4 w-4 flex-shrink-0 text-gray-500" aria-hidden="true" />}
          {option.title}
        </span>
        {option.sub && <span className="w-full break-words text-xs text-gray-500">{option.sub}</span>}
      </li>
    );
  }

  const loading = cases.isLoading;
  const failed = cases.isError;
  const noMatches = !loading && !failed && options.length === 0;

  return (
    <div className={cn("space-y-2", className)}>
      <label htmlFor={inputId} className="sr-only">
        Search your cases
      </label>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" aria-hidden="true" />
        <input
          id={inputId}
          type="search"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={activeOption ? `${listId}-${activeOption.id}` : undefined}
          autoComplete="off"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Search by title, case number or party"
          className="h-11 w-full rounded-lg border border-gray-200 bg-surface pl-8 pr-3 text-sm placeholder:text-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary md:h-9"
        />
      </div>

      {loading && (
        <p role="status" className="px-1 py-1 text-sm text-gray-500">
          Loading your cases.
        </p>
      )}
      {failed && (
        <div role="alert" className="space-y-2 rounded-lg border border-red-200 bg-red-50 p-3">
          <p className="text-sm text-red-800">Your cases could not be loaded.</p>
          <Button type="button" variant="secondary" size="sm" onClick={() => cases.refetch()}>
            Try again
          </Button>
        </div>
      )}
      {noMatches && (
        <p className="px-1 py-3 text-sm text-gray-500">{needle ? "No case matches that search." : "You have no cases yet."}</p>
      )}

      {options.length > 0 && (
        <div id={listId} role="listbox" aria-label="Choose what to ask about" className="max-h-72 overflow-y-auto overscroll-contain">
          {showPractice && <ul role="presentation" className="mb-1">{row(options[0])}</ul>}
          {sections.map((section) => (
            <div key={section.key} role="group" aria-label={section.label}>
              <p className="px-2 pb-0.5 pt-2 text-xs font-semibold uppercase tracking-wide text-gray-500">{section.label}</p>
              <ul role="presentation">{options.filter((option) => option.section === section.key).map(row)}</ul>
            </div>
          ))}
        </div>
      )}

      {onCancel && (
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Back
        </Button>
      )}
    </div>
  );
}
