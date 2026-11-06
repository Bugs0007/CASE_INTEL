"use client";

import { useId, useMemo, useState } from "react";
import { AlertTriangle, Landmark, MapPin, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { HighCourtInfo } from "@/types";
import { Panel } from "./ui";

/** The way to choose a High Court without the map: a search box that is a proper
 * combobox (arrow keys, Enter, Escape, screen-reader roles) and a grid of every
 * court. A court the advocate search cannot reach is greyed, not clickable, and
 * says why on hover and to a screen reader. */
export function HighCourtPicker({
  courts,
  selected,
  onSelect,
  loadError,
  onRetry,
  extra,
}: {
  courts: HighCourtInfo[];
  selected: string | null;
  onSelect: (code: string) => void;
  loadError?: boolean;
  onRetry?: () => void;
  /** More to show under the grid (the map, once it is approved). */
  extra?: React.ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return courts.filter((c) => !q || c.name.toLowerCase().includes(q));
  }, [courts, query]);

  const choose = (court: HighCourtInfo) => {
    if (!court.supported) return;
    onSelect(court.code);
    setQuery("");
    setOpen(false);
  };

  return (
    <Panel
      title="Choose a High Court"
      icon={<MapPin className="h-[17px] w-[17px]" />}
      sub="Pick a court"
      label="Choose a High Court"
      className="h-full"
      bodyClassName="gap-3 overflow-hidden"
      action={
        <div className="relative w-[230px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-500" />
          <input
            role="combobox"
            aria-expanded={open}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={open && matches[active] ? `${listId}-${matches[active].code}` : undefined}
            aria-label="Search a High Court"
            placeholder="Search a High Court"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
              setActive(0);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 120)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setOpen(true);
                setActive((i) => Math.min(i + 1, matches.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter" && open && matches[active]) {
                e.preventDefault();
                choose(matches[active]);
              } else if (e.key === "Escape") {
                setOpen(false);
              }
            }}
            className="h-[30px] w-full rounded-md border border-gray-300 bg-surface pl-8 pr-2 text-[13px] outline-none focus:ring-2 focus:ring-primary"
          />
          {open && (
            <ul
              id={listId}
              role="listbox"
              aria-label="High Courts"
              className="absolute right-0 z-20 mt-1 max-h-64 w-72 overflow-y-auto rounded-md border border-gray-200 bg-surface py-1 shadow-card"
            >
              {matches.length === 0 && <li className="px-3 py-2 text-xs text-gray-500">No High Court matches.</li>}
              {matches.map((c, i) => (
                <li
                  key={c.code}
                  id={`${listId}-${c.code}`}
                  role="option"
                  aria-selected={c.code === selected}
                  aria-disabled={!c.supported}
                  title={c.supported ? undefined : c.support_note}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(c);
                  }}
                  className={cn(
                    "px-3 py-1.5 text-[13px]",
                    i === active && "bg-gray-100",
                    c.supported ? "cursor-pointer" : "cursor-not-allowed text-gray-400",
                  )}
                >
                  {c.name}
                  {!c.supported && <span className="ml-1 text-[11px]">(not available)</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      }
    >
      {loadError ? (
        <div role="alert" className="flex items-start gap-2 rounded-md border border-status-alert bg-status-alert-soft p-3 text-sm text-status-alert">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            The list of High Courts did not load.{" "}
            {onRetry && (
              <button type="button" onClick={onRetry} className="font-semibold underline">
                Retry
              </button>
            )}
          </span>
        </div>
      ) : (
        <ul aria-label="High Courts" className="grid min-h-0 flex-1 grid-cols-2 content-start gap-2 overflow-y-auto pr-1 xl:grid-cols-3">
          {courts.map((c) => (
            <li key={c.code}>
              <button
                type="button"
                disabled={!c.supported}
                aria-pressed={c.code === selected}
                title={c.supported ? undefined : c.support_note}
                onClick={() => choose(c)}
                className={cn(
                  "flex h-full w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                  c.code === selected ? "border-primary bg-primary text-page" : "border-gray-200 bg-surface hover:bg-gray-50",
                  !c.supported && "cursor-not-allowed bg-gray-50 text-gray-400 hover:bg-gray-50",
                )}
              >
                <Landmark className="h-3.5 w-3.5 shrink-0" />
                <span className="min-w-0">
                  <span className="block truncate font-semibold">{c.name.replace(" High Court", "")}</span>
                  {!c.supported && <span className="block text-[11px]">Not available</span>}
                  {c.supported && c.registry_benches.length > 0 && (
                    <span className="block text-[11px] opacity-70">{c.registry_benches.length + 1} benches</span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {extra}
    </Panel>
  );
}
