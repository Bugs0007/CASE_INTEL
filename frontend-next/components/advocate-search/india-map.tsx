"use client";

import { useEffect, useRef, useState } from "react";
import india from "@svg-maps/india";
import { COURT_OF_LOCATION, MAP_CREDIT, SMALL_LOCATIONS, JURISDICTION } from "@/lib/hc-jurisdiction";
import { cn } from "@/lib/utils";
import type { HighCourtInfo } from "@/types";

const [, , VW, VH] = india.viewBox.split(" ").map(Number);

/**
 * A map of India for choosing a High Court. The outlines are @svg-maps/india's own
 * paths, untouched (CC BY 4.0, credited under the map). It is for choosing a court
 * only: hovering a state lights its whole High Court group, a click selects it,
 * the chosen court gets a label card, and a court the search cannot reach is greyed
 * and not clickable. Every state is also a keyboard stop with a name, and the small
 * ones have buttons in a column beside the map.
 */
export function IndiaMap({
  courts,
  selected,
  onSelect,
}: {
  courts: HighCourtInfo[];
  selected: string | null;
  onSelect: (code: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const byCode = new Map(courts.map((c) => [c.code, c]));
  const selectedCourt = selected ? byCode.get(selected) : undefined;
  const mainId = selected ? JURISDICTION[selected]?.[0] : undefined;
  const mainPath = useRef<SVGPathElement | null>(null);
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);

  // Where to hang the label card: the centre of the court's first state.
  useEffect(() => {
    const el = mainPath.current;
    if (!selected || !el || typeof el.getBBox !== "function") return setAnchor(null);
    const b = el.getBBox();
    setAnchor({ x: ((b.x + b.width / 2) / VW) * 100, y: ((b.y + b.height / 2) / VH) * 100 });
  }, [selected, mainId]);

  const choose = (code: string | undefined) => {
    const court = code ? byCode.get(code) : undefined;
    if (court?.supported) onSelect(court.code);
  };

  const fillFor = (id: string) => {
    const code = COURT_OF_LOCATION[id];
    const court = code ? byCode.get(code) : undefined;
    if (!court || !court.supported) return "fill-[#ecebe6]";
    if (code === selected) return "fill-[#1b2d4b]";
    if (code === hover) return "fill-[#e3c27a]";
    return "fill-[#dfe5ee]";
  };

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_150px] overflow-hidden" data-testid="india-map">
      <div className="relative flex min-h-0 items-center justify-center bg-[radial-gradient(ellipse_at_50%_40%,#fff_0,#f6f4ee_100%)] px-2.5 py-1.5">
        <svg
          viewBox={india.viewBox}
          role="group"
          aria-label="Map of India. Choose a High Court by its state or territory."
          className="h-full max-h-full w-auto"
        >
          {india.locations.map((loc) => {
            const code = COURT_OF_LOCATION[loc.id];
            const court = code ? byCode.get(code) : undefined;
            const usable = !!court?.supported;
            return (
              <path
                key={loc.id}
                ref={loc.id === mainId ? mainPath : undefined}
                d={loc.path}
                data-location={loc.id}
                role="button"
                tabIndex={usable ? 0 : -1}
                aria-label={`${loc.name}: ${court?.name ?? "no High Court listed"}${usable ? "" : " (not available)"}`}
                aria-pressed={code === selected}
                aria-disabled={!usable}
                className={cn(
                  "stroke-white outline-none transition-[fill] duration-200 motion-reduce:transition-none [stroke-width:1.1]",
                  usable ? "cursor-pointer" : "cursor-not-allowed",
                  fillFor(loc.id),
                  "focus-visible:[stroke:#e3c27a] focus-visible:[stroke-width:2.5]",
                )}
                onMouseEnter={() => usable && setHover(code)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => usable && setHover(code)}
                onBlur={() => setHover(null)}
                onClick={() => choose(code)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    choose(code);
                  }
                }}
              >
                <title>{`${loc.name}: ${court?.name ?? "no High Court listed"}${court && !court.supported ? ` (${court.support_note})` : ""}`}</title>
              </path>
            );
          })}
        </svg>

        {selectedCourt && anchor && (
          <div
            className="pointer-events-none absolute rounded-lg border border-gray-200 bg-surface px-2.5 py-1.5 shadow-card"
            style={{ left: `${Math.min(Math.max(anchor.x, 20), 72)}%`, top: `${Math.min(anchor.y + 6, 90)}%` }}
          >
            <b className="block font-serif text-[13px] leading-tight">{selectedCourt.name}</b>
            <span className="block text-[10px] text-gray-500">
              Selected{JURISDICTION[selectedCourt.code]?.length > 1 ? ` · ${JURISDICTION[selectedCourt.code].length} states/UTs` : ""}
            </span>
          </div>
        )}

        <p className="pointer-events-none absolute bottom-2 left-3 flex gap-3 text-[11.5px] text-gray-600">
          <span><i className="mr-1 inline-block h-[11px] w-[11px] rounded-[3px] bg-[#1b2d4b] align-[-1px]" />Selected</span>
          <span><i className="mr-1 inline-block h-[11px] w-[11px] rounded-[3px] bg-[#e3c27a] align-[-1px]" />Hover</span>
          <span><i className="mr-1 inline-block h-[11px] w-[11px] rounded-[3px] bg-[#dfe5ee] align-[-1px]" />Available</span>
        </p>
        <p className="pointer-events-none absolute bottom-2 right-3 max-w-[60%] text-right text-[10.5px] text-gray-400">{MAP_CREDIT}</p>
      </div>

      <div className="flex min-h-0 flex-col gap-1.5 overflow-y-auto border-l border-gray-200 bg-surface p-2.5">
        <span className="font-mono text-[10.5px] font-medium uppercase tracking-[0.1em] text-gray-500">Small states and UTs</span>
        {SMALL_LOCATIONS.map((s) => {
          const code = COURT_OF_LOCATION[s.ids[0]];
          const court = byCode.get(code);
          const on = code === selected;
          return (
            <button
              key={s.label}
              type="button"
              disabled={!court?.supported}
              aria-pressed={on}
              title={court && !court.supported ? court.support_note : court?.name}
              onClick={() => choose(code)}
              onMouseEnter={() => court?.supported && setHover(code)}
              onMouseLeave={() => setHover(null)}
              className={cn(
                "flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
                on ? "border-primary bg-primary text-page" : "border-gray-200 bg-surface hover:bg-gray-50",
                !court?.supported && "cursor-not-allowed opacity-50",
              )}
            >
              <i className="h-2 w-2 shrink-0 rounded-full bg-[#aab4c4]" />
              {s.label}
            </button>
          );
        })}
        <span className="flex-1" />
        <p className="text-[11px] text-gray-500">Too small to click on the map? Pick here.</p>
      </div>
    </div>
  );
}
