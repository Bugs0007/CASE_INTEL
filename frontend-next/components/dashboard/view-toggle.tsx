"use client";

import { useRef, type KeyboardEvent } from "react";
import { FileText, LayoutGrid, type LucideIcon } from "lucide-react";
import type { DashboardView } from "@/hooks/use-dashboard-view";
import { cn } from "@/lib/utils";

const TABS: { id: DashboardView; label: string; icon: LucideIcon }[] = [
  { id: "brief", label: "Briefing", icon: FileText },
  { id: "map", label: "Practice map", icon: LayoutGrid },
];

export const tabId = (view: DashboardView) => `dash-tab-${view}`;
export const panelId = (view: DashboardView) => `dash-panel-${view}`;

/** Briefing | Practice map. A tablist: Left/Right (and Home/End) move
 * between the two, and each tab controls a tabpanel the page renders. */
export function ViewToggle({
  view,
  onChange,
}: {
  view: DashboardView;
  onChange: (view: DashboardView) => void;
}) {
  const refs = useRef<Partial<Record<DashboardView, HTMLButtonElement | null>>>({});

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    let next: DashboardView | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") next = view === "brief" ? "map" : "brief";
    else if (event.key === "Home") next = "brief";
    else if (event.key === "End") next = "map";
    if (!next) return;
    event.preventDefault();
    onChange(next);
    refs.current[next]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Dashboard view"
      onKeyDown={onKeyDown}
      className="inline-flex gap-0.5 rounded-[7px] border border-gray-200 bg-[var(--ci-paper-2)] p-[3px]"
    >
      {TABS.map((tab) => {
        const selected = tab.id === view;
        const Icon = tab.icon;
        return (
          <button
            key={tab.id}
            ref={(el) => {
              refs.current[tab.id] = el;
            }}
            id={tabId(tab.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={panelId(tab.id)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 whitespace-nowrap rounded-[5px] px-3.5 text-[13.5px] font-semibold transition-colors md:h-8",
              selected
                ? "bg-surface text-gray-900 shadow-[0_1px_2px_rgba(14,26,44,0.14),0_0_0_1px_var(--ci-ink-14)]"
                : "text-gray-600 hover:text-gray-900",
            )}
          >
            <Icon className="h-3.5 w-3.5" strokeWidth={1.8} aria-hidden="true" />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
